"""Experimental final-reply LoRA, CPU preflight, saved-weight reload verification."""

from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import random
import time
from .common import (
    PROJECT,
    WORKSPACE,
    canonical,
    new_output,
    sha,
    source_state,
    write_json,
)
from .data import evaluation_texts
from .runner import gpu_lease, local_model


def encode_record(tokenizer, row, max_length):
    messages = row["messages"]
    if (
        len(messages) < 3
        or messages[0]["role"] != "system"
        or messages[-1]["role"] != "assistant"
        or messages[-2]["role"] != "user"
    ):
        raise ValueError("Final assistant target required")
    for i, m in enumerate(messages[1:]):
        if (
            m["role"] != ("user" if i % 2 == 0 else "assistant")
            or not isinstance(m["content"], str)
            or not m["content"].strip()
        ):
            raise ValueError("Invalid message order/content")
    prefix = tokenizer.apply_chat_template(
        messages[:-1], tokenize=True, add_generation_prompt=True, enable_thinking=False
    )
    answer = tokenizer.encode(messages[-1]["content"], add_special_tokens=False)
    ids = prefix + answer + [tokenizer.eos_token_id]
    if not answer or len(ids) > max_length:
        raise ValueError("Empty target or overlength")
    return {
        "id": row["id"],
        "input_ids": ids,
        "labels": [-100] * len(prefix) + answer + [tokenizer.eos_token_id],
    }


def _actual_dialogue_hash(row):
    if (
        not isinstance(row, dict)
        or not isinstance(row.get("id"), str)
        or not row["id"].strip()
        or not isinstance(row.get("messages"), list)
        or len(row["messages"]) < 3
        or len(row["messages"]) % 2 != 1
    ):
        raise ValueError("Invalid training conversation")
    messages = row["messages"]
    for index, message in enumerate(messages):
        role = "system" if index == 0 else ("user" if index % 2 else "assistant")
        if (
            not isinstance(message, dict)
            or message.get("role") != role
            or not isinstance(message.get("content"), str)
            or not message["content"].strip()
        ):
            raise ValueError("Invalid training conversation")
    provenance = row.get("provenance")
    declared = provenance.get("content_sha256") if isinstance(provenance, dict) else None
    dialogue_hash = hashlib.sha256(canonical(messages[1:]).encode()).hexdigest()
    full_hash = hashlib.sha256(canonical(messages).encode()).hexdigest()
    # Original exports hash the dialogue; synthetic SDK exports hash the full prompt.
    if not isinstance(declared, str) or declared not in (dialogue_hash, full_hash):
        raise ValueError("Invalid training content provenance")
    if not isinstance(provenance.get("source"), str) or not provenance["source"].strip():
        raise ValueError("Invalid training content provenance")
    return dialogue_hash


def load_data(data):
    data = Path(data)
    manifest = json.loads(data.with_name("manifest.json").read_text())
    if (
        manifest["purpose"] != "experimental-style-pilot"
        or manifest["adapter_scope"] != "reply-only"
        or manifest["human_reviewed"] is not False
    ):
        raise ValueError("Expected explicit automatic-only pilot provenance")
    if (
        sha(data) != manifest["sft_sha256"]
        or sha(data.with_name("dev.jsonl")) != manifest["dev_sha256"]
    ):
        raise ValueError("Dataset manifest hash mismatch")
    from . import data as data_module

    if manifest.get("screening_code_sha256") != sha(Path(data_module.__file__)):
        raise ValueError("Screening implementation changed; rebuild pilot export")
    protected_texts, protected = evaluation_texts()
    if protected != manifest["protected_eval_hashes"]:
        raise ValueError("Evaluation corpus changed; rescreen data")
    train = [json.loads(x) for x in data.read_text().splitlines() if x.strip()]
    dev = [
        json.loads(x)
        for x in data.with_name("dev.jsonl").read_text().splitlines()
        if x.strip()
    ]
    if len(train) != manifest["samples"] or not train or len(train) > 200:
        raise ValueError("Pilot training sample count must be 1..200")
    if len(dev) != manifest.get("dev_samples"):
        raise ValueError("Development sample count differs from manifest")
    actual_train = {_actual_dialogue_hash(row) for row in train}
    actual_dev = {_actual_dialogue_hash(row) for row in dev}
    train_ids = {r["id"] for r in train}
    dev_ids = {r["id"] for r in dev}
    if len(train_ids) != len(train) or len(dev_ids) != len(dev) or train_ids & dev_ids:
        raise ValueError("Split identity leakage")
    a = {r["provenance"]["content_sha256"] for r in train}
    b = {r["provenance"]["content_sha256"] for r in dev}
    if a & b:
        raise ValueError("Duplicate content across splits")
    if actual_train & actual_dev:
        raise ValueError("Duplicate actual dialogue across splits")
    candidates = []
    policy = {}
    for row in train + dev:
        source = row["provenance"]["source"]
        policy[source] = {"use": "experimental-sft"}
        candidates.append(data_module.normalize_dialogue(
            source, "train", row["id"], [m["content"] for m in row["messages"][1:]]
        ))
    _, rejected = data_module.screen_candidates(candidates, protected_texts, source_policy=policy)
    # Exported pilots may intentionally repeat templates. Actual cross-split
    # duplicates are checked above; these export selection rules are separate.
    for row in rejected:
        reasons = set(row["reasons"]) - {"duplicate", "near_duplicate"}
        if reasons:
            raise ValueError("Training data screening rejected: " + ", ".join(sorted(reasons)))
    return train, dev, manifest


def preflight(data, model_path, output, config):
    from transformers import AutoTokenizer

    cfg = json.loads(Path(config).read_text())
    train, dev, manifest = load_data(data)
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    output = new_output(output)
    accepted = []
    rejected = []
    dev_tokens = []
    for split, rows, destination in [
        ("train", train, accepted),
        ("dev", dev, dev_tokens),
    ]:
        for row in rows:
            try:
                destination.append(encode_record(tokenizer, row, cfg["max_length"]))
            except ValueError as exc:
                rejected.append({"id": row["id"], "split": split, "reason": str(exc)})
    write_json(output / "tokens.json", {"train": accepted, "dev": dev_tokens})
    tokenizer_hashes = {
        p.name: sha(p)
        for p in Path(model_path).iterdir()
        if p.is_file()
        and (
            p.name.startswith("tokenizer")
            or p.name in ("vocab.json", "merges.txt", "chat_template.jinja")
        )
    }
    report = {
        "purpose": "cpu-tokenization-preflight",
        "samples": len(accepted),
        "dev_samples": len(dev_tokens),
        "rejected": rejected,
        "dataset_manifest_sha256": sha(Path(data).with_name("manifest.json")),
        "data_sha256": sha(data),
        "config_sha256": sha(config),
        "tokenizer_files": tokenizer_hashes,
        "tokens_sha256": sha(output / "tokens.json"),
        "supervised_tokens": sum(
            sum(v != -100 for v in row["labels"]) for row in accepted
        ),
        "sequence_lengths": [len(r["input_ids"]) for r in accepted],
        "human_reviewed": False,
        "quality_approved": False,
        "supervision": "final-assistant-only; all prompt/history tokens masked",
        "adapters_in_analysis": False,
    }
    write_json(output / "preflight.json", report)
    if not accepted:
        raise ValueError("No samples survived tokenization")
    return report


def train(data, lock_path, model_name, config, output, *, gpus):
    cfg = json.loads(Path(config).read_text())
    lock = json.loads(Path(lock_path).read_text())
    entry = next(m for m in lock["models"] if m["name"] == model_name)
    if entry["gpus"] != 1:
        raise ValueError(
            "This pilot trainer supports single-GPU 4B/14B only; 32B inference is supported separately"
        )
    rows, dev_rows, data_manifest = load_data(data)
    if (
        not 1 <= cfg["max_steps"] <= 100
        or not 1 <= cfg["gradient_accumulation_steps"] <= 16
    ):
        raise ValueError("Invalid pilot step configuration")
    with gpu_lease(list(gpus), 1):
        model_path = local_model(entry)
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM
        from peft import LoraConfig, get_peft_model

        random.seed(cfg["seed"])
        torch.manual_seed(cfg["seed"])
        tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
        examples = []
        dev = []
        rejected = []
        for split, source, destination in [
            ("train", rows, examples),
            ("dev", dev_rows, dev),
        ]:
            for row in source:
                try:
                    destination.append(encode_record(tokenizer, row, cfg["max_length"]))
                except ValueError:
                    rejected.append(
                        {"id": row["id"], "split": split, "reason": "overlength"}
                    )
        if not examples:
            raise ValueError("No trainable examples")
        output = new_output(output)
        manifest = {
            "purpose": "experimental-style-pilot",
            "quality_approved": False,
            "human_reviewed": False,
            "base_model_id": entry["repo"],
            "base_revision": entry["revision"],
            "base_weights": entry["files"],
            "dataset_sha256": sha(data),
            "dataset_manifest_sha256": sha(Path(data).with_name("manifest.json")),
            "config": cfg,
            "adapter_scope": "reply-only",
            "supervision": "final-assistant-only",
            "backend": source_state(),
            "samples": len(examples),
            "dev_samples": len(dev),
            "rejected": rejected,
            "physical_gpus": gpus,
            "status": "running",
            "training_pid": os.getpid(),
        }
        write_json(output / "manifest.json", manifest)
        try:
            model = AutoModelForCausalLM.from_pretrained(
                model_path,
                local_files_only=True,
                dtype=torch.bfloat16,
                attn_implementation="sdpa",
            ).to("cuda")
            model = get_peft_model(
                model,
                LoraConfig(
                    r=cfg["lora_r"],
                    lora_alpha=cfg["lora_alpha"],
                    lora_dropout=cfg["lora_dropout"],
                    target_modules=cfg["target_modules"],
                    task_type="CAUSAL_LM",
                    bias="none",
                ),
            )
            model.config.use_cache = False
            model.gradient_checkpointing_enable(
                gradient_checkpointing_kwargs={"use_reentrant": False}
            )
            params = [p for p in model.parameters() if p.requires_grad]
            optimizer = torch.optim.AdamW(
                params, lr=cfg["learning_rate"], weight_decay=0
            )
            order = list(range(len(examples)))
            random.shuffle(order)
            accum = cfg["gradient_accumulation_steps"]
            steps = min(cfg["max_steps"], (len(examples) + accum - 1) // accum)
            log = []
            start = time.perf_counter()
            torch.cuda.reset_peak_memory_stats()
            for step in range(steps):
                batch_ids = order[step * accum : (step + 1) * accum]
                model.train()
                optimizer.zero_grad(set_to_none=True)
                loss_sum = 0.0
                for index in batch_ids:
                    item = examples[index]
                    batch = {
                        k: torch.tensor([item[k]], device="cuda")
                        for k in ("input_ids", "labels")
                    }
                    loss = model(**batch).loss
                    if not torch.isfinite(loss):
                        raise ValueError("Non-finite training loss")
                    (loss / len(batch_ids)).backward()
                    loss_sum += loss.item() / len(batch_ids)
                grad = torch.nn.utils.clip_grad_norm_(
                    params, 1.0, error_if_nonfinite=True
                )
                optimizer.step()
                log.append(
                    {
                        "step": step + 1,
                        "loss": loss_sum,
                        "gradient_norm": float(grad),
                        "samples": len(batch_ids),
                    }
                )
                write_json(output / "steps.json", log)
            if not any(
                p.detach().abs().max().item() > 0
                for n, p in model.named_parameters()
                if "lora_B" in n
            ):
                raise ValueError("Adapter weights did not update")
            model.eval()
            model.config.use_cache = True
            with torch.inference_mode():
                losses = []
                for row in dev:
                    batch = {
                        k: torch.tensor([row[k]], device="cuda")
                        for k in ("input_ids", "labels")
                    }
                    losses.append(float(model(**batch).loss))
                probe_row = next(row for row in rows if row["id"] == examples[0]["id"])
                probe = _probe(model, tokenizer, probe_row, torch)
            torch.save(probe["logits"], output / "probe.pt")
            model.save_pretrained(output / "adapter", safe_serialization=True)
            tokenizer.save_pretrained(output / "adapter")
            manifest.update(
                status="completed",
                steps=steps,
                training_seconds=time.perf_counter() - start,
                dev_loss=sum(losses) / len(losses) if losses else None,
                dev_loss_is_not_quality=True,
                adapter_sha256=sha(output / "adapter/adapter_model.safetensors"),
                adapter_config_sha256=sha(output / "adapter/adapter_config.json"),
                probe_text=probe["text"],
                probe_source_id=probe_row["id"],
                peak_gpu_bytes=torch.cuda.max_memory_allocated(),
                trainable_parameters=sum(p.numel() for p in params),
            )
            write_json(output / "manifest.json", manifest)
            return manifest
        except Exception as exc:
            manifest.update(status="failed", error_type=type(exc).__name__)
            write_json(output / "manifest.json", manifest)
            raise


def _probe(model, tokenizer, row, torch):
    ids = tokenizer.apply_chat_template(
        row["messages"][:-1],
        tokenize=True,
        add_generation_prompt=True,
        enable_thinking=False,
        return_tensors="pt",
    ).to("cuda")
    with torch.inference_mode():
        logits = model(ids).logits[0, -1].float().cpu()
        result = model.generate(
            ids,
            attention_mask=torch.ones_like(ids),
            max_new_tokens=64,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )
    return {
        "logits": logits,
        "text": tokenizer.decode(result[0, ids.shape[1] :], skip_special_tokens=True),
    }


def verify_reload(data, lock_path, model_name, output, *, gpus):
    lock = json.loads(Path(lock_path).read_text())
    entry = next(m for m in lock["models"] if m["name"] == model_name)
    output = Path(output)
    manifest = json.loads((output / "manifest.json").read_text())
    if manifest.get("training_pid") == os.getpid():
        raise ValueError("Reload verification must use a fresh Python process")
    if (
        manifest["status"] != "completed"
        or manifest["base_model_id"] != entry["repo"]
        or manifest["base_revision"] != entry["revision"]
        or manifest["dataset_sha256"] != sha(data)
    ):
        raise ValueError("Training/base/data mismatch")
    if (
        sha(output / "adapter/adapter_model.safetensors") != manifest["adapter_sha256"]
        or sha(output / "adapter/adapter_config.json")
        != manifest["adapter_config_sha256"]
    ):
        raise ValueError("Adapter hash mismatch")
    train_rows, _, _ = load_data(data)
    row = next(r for r in train_rows if r["id"] == manifest["probe_source_id"])
    with gpu_lease(list(gpus), 1):
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM
        from peft import PeftModel

        path = local_model(entry)
        tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
        model = PeftModel.from_pretrained(
            AutoModelForCausalLM.from_pretrained(
                path,
                local_files_only=True,
                dtype=torch.bfloat16,
                attn_implementation="sdpa",
            ).to("cuda"),
            output / "adapter",
            is_trainable=False,
        ).eval()
        probe = _probe(model, tokenizer, row, torch)
        saved = torch.load(output / "probe.pt", map_location="cpu", weights_only=True)
        good = (
            torch.allclose(saved, probe["logits"], atol=1e-4, rtol=1e-4)
            and probe["text"] == manifest["probe_text"]
            and bool(probe["text"].strip())
        )
        report = {
            "passed": good,
            "fresh_process_required": True,
            "max_logit_difference": float((saved - probe["logits"]).abs().max()),
            "generation_identical": probe["text"] == manifest["probe_text"],
            "semantic_quality": "unscored",
        }
        write_json(output / "reload-verification.json", report)
        if not good:
            raise ValueError("Fresh-process adapter reload failed")
        return report
