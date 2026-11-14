"""Capture the existing backend's actual model.generate boundary, without retries."""
import hashlib
import json
import os
from pathlib import Path
from time import time as actual_wallclock


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False,
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_call(row):
    """Validate observations taken inside the adapter scope, before generation."""
    ids = row["input_ids"]
    require(isinstance(ids, list) and len(ids) == 1 and bool(ids[0]), "one nonempty sequence required")
    require(all(type(n) is int and n >= 0 for n in ids[0]), "invalid token IDs")
    require(ids == [row["independent_token_ids"]], "actual/template token mismatch")
    require(row["attention_mask"] == [[1] * len(ids[0])], "actual attention mask mismatch")
    require(all(type(n) is int for n in row["attention_mask"][0]), "mask values must be integers")
    require(row["kind"] in ("analysis", "reply"), "invalid generation role")
    require(type(row["adapter_requested"]) is bool and type(row["has_adapter"]) is bool,
        "adapter flags must be booleans")
    require(not row["adapter_requested"] or row["has_adapter"], "missing adapter")
    require(row["kind"] != "analysis" or not row["adapter_requested"], "analysis adapter forbidden")
    states = row["lora_layers"]
    require(bool(states) == row["has_adapter"], "actual LoRA layer presence mismatch")
    for state in states:
        require(type(state["disabled"]) is bool and state["disabled"] is not row["adapter_requested"],
            "actual LoRA disable state mismatch")
        require(state["training"] is False, "LoRA layer remains in training mode")
    require(row["model_training"] is False, "model remains in training mode")
    require(row["embedding_dtype"] == "torch.bfloat16", "BF16 base required")
    require(row["embedding_device"].startswith("cuda:"), "CUDA model required")
    require(row["do_sample"] is False, "greedy generation required")
    require(type(row["max_new_tokens"]) is int and row["max_new_tokens"] == row["registered_limit"],
        "generation limit mismatch")
    require(len(ids[0]) + row["max_new_tokens"] <= row["context_tokens"], "context budget exceeded")
    require(row["analysis_grammar_present"] is (row["kind"] == "analysis"), "grammar role mismatch")


class CapturedBackend:
    """Composition preserves production generation and records its real entry."""

    def __init__(self, backend, output):
        from avatar.lab.runner import TransformersBackend, validate_settings
        require(type(backend) is TransformersBackend, "actual production TransformersBackend required")
        validate_settings(backend.settings)
        self.backend = backend
        self.calls = []
        self.context = {}
        self.pending = None
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=False)
        self.original_generate = backend.model.generate
        backend.model.generate = self._actual_generate

    def write(self, name, value):
        with (self.output / name).open("x") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())

    def _actual_generate(self, *args, **kwargs):
        require(self.pending is not None, "unregistered model.generate call")
        from peft.tuners.lora.layer import LoraLayer
        row = self.pending
        require(row["actual_generate_entries"] == 0, "multiple generate calls in one interface turn")
        row["actual_generate_entries"] += 1
        ids = args[0] if args else kwargs["input_ids"]
        model = self.backend.model
        embedding = model.get_input_embeddings().weight
        row.update(input_ids=ids.detach().cpu().tolist(),
            attention_mask=kwargs["attention_mask"].detach().cpu().tolist(),
            embedding_dtype=str(embedding.dtype), embedding_device=str(embedding.device),
            model_training=model.training,
            lora_layers=[{"name": name, "disabled": layer.disable_adapters,
                "training": layer.training} for name, layer in model.named_modules()
                if isinstance(layer, LoraLayer)],
            do_sample=kwargs.get("do_sample"), max_new_tokens=kwargs.get("max_new_tokens"),
            pad_token_id=kwargs.get("pad_token_id"),
            analysis_grammar_present=callable(kwargs.get("prefix_allowed_tokens_fn")))
        self.write(f'{row["ordinal"]:04}-entry.json', row)
        validate_call(row)
        output = self.original_generate(*args, **kwargs)
        values = output.detach().cpu().tolist()
        require(len(values) == 1 and values[0][:len(row["input_ids"][0])] == row["input_ids"][0],
            "generation output prefix mismatch")
        row["actual_output_ids"] = values
        return output

    def generate(self, messages, kind, adapter):
        require(self.pending is None, "overlapping generation forbidden")
        settings = self.backend.settings
        row = {"ordinal": len(self.calls) + 1, "kind": kind,
            "adapter_requested": adapter, "has_adapter": self.backend.has_adapter,
            "messages": json.loads(json.dumps(messages, ensure_ascii=False)),
            "context": dict(self.context), "actual_generate_entries": 0,
            "actual_wallclock_epoch": actual_wallclock(), "fixture": False,
            "registered_limit": settings["analysis_tokens" if kind == "analysis" else "reply_tokens"],
            "context_tokens": settings["context_tokens"], "completed": False}
        row["messages_sha256"] = digest(row["messages"])
        row["independent_token_ids"] = self.backend.tokenizer.apply_chat_template(messages,
            tokenize=True, add_generation_prompt=True, enable_thinking=False)
        self.calls.append(row)
        self.pending = row
        try:
            result = self.backend.generate(messages, kind, adapter)
            require(row["actual_generate_entries"] == 1 and "actual_output_ids" in row,
                "production backend did not complete one observed generate")
            require(result["adapter_enabled"] is adapter, "interface adapter flag mismatch")
            row.update(completed=True, backend_result=result)
            return result
        except BaseException as error:
            row["failure"] = type(error).__name__ + ": " + str(error)[:500]
            raise
        finally:
            self.write(f'{row["ordinal"]:04}-result.json', row)
            self.pending = None
