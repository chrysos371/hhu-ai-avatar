"""Same-backend model-size and reply-only style ablations, with resource gates."""

from __future__ import annotations
from contextlib import ExitStack, contextmanager
import hashlib
import json
import logging
import os
from pathlib import Path
import random
import subprocess
import tempfile
import time
from .checks import assess, compare_reports
from .common import (
    PROJECT,
    WORKSPACE,
    canonical,
    get_json,
    new_output,
    sha,
    source_state,
    write_json,
)

STYLE_HINT = "表达要求：先回应用户具体内容，自然、温和、少套话；普通闲聊默认简短，复杂任务按需展开。用户只想倾听时不催促行动，不必每轮提问。只调整表达，不改变事实、角色归属、工具边界或安全决定。"
ARMS = ("base", "style_prompt", "style_lora")


def gpu_inventory():
    raw = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=index,memory.free,memory.used,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        text=True,
    )
    return {
        int(v[0]): {
            "free_mib": int(v[1]),
            "used_mib": int(v[2]),
            "utilization": int(v[3]),
        }
        for line in raw.splitlines()
        if (v := line.split(","))
    }


def validate_gpu_selection(gpus, cards, *, required_cards):
    if (
        len(gpus) != required_cards
        or not 1 <= len(gpus) <= 4
        or len(set(gpus)) != len(gpus)
    ):
        raise ValueError("Wrong GPU count; maximum four unique GPUs")
    if (
        any(type(i) is not int or i < 0 for i in gpus)
        or len({i // 4 for i in gpus}) != 1
    ):
        raise ValueError("GPUs must belong to the same group of four")
    if any(
        i not in cards or cards[i]["used_mib"] > 1024 or cards[i]["free_mib"] < 36000
        for i in gpus
    ):
        raise ValueError("Selected GPUs are busy or lack 36,000 MiB free each")


@contextmanager
def gpu_lease(gpus, required_cards):
    import fcntl

    folder = WORKSPACE / "runtime/gpu-leases"
    folder.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        for index in sorted(gpus):
            f = stack.enter_context((folder / f"gpu-{index}.lock").open("a"))
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        validate_gpu_selection(gpus, gpu_inventory(), required_cards=required_cards)
        os.environ["CUDA_VISIBLE_DEVICES"] = ",".join(map(str, gpus))
        os.environ["HF_HOME"] = str(WORKSPACE / "hf-cache")
        os.environ["TMPDIR"] = str(WORKSPACE / "runtime/tmp")
        yield


def validate_settings(settings):
    if (
        settings.get("dtype") != "bfloat16"
        or settings.get("attention") != "sdpa"
        or settings.get("do_sample") is not False
        or settings.get("enable_thinking") is not False
    ):
        raise ValueError(
            "Only fixed BF16/SDPA greedy non-thinking comparisons are supported"
        )
    for key in ("seed", "reply_tokens", "analysis_tokens", "context_tokens"):
        if type(settings.get(key)) is not int or settings[key] < 0:
            raise ValueError("Invalid generation limits")
    if (
        not 1 <= settings["reply_tokens"] <= 1024
        or not 1 <= settings["analysis_tokens"] <= 1024
        or not 1024 <= settings["context_tokens"] <= 32768
    ):
        raise ValueError("Invalid generation budget")


def lock_models(config, output):
    output = new_output(output)
    cfg = json.loads(Path(config).read_text())
    validate_settings(cfg["generation"])
    models = []
    for entry in cfg["models"]:
        row = dict(entry)
        try:
            revision = entry.get("revision", "main")
            metadata = get_json(
                f"https://huggingface.co/api/models/{entry['repo']}/revision/{revision}?blobs=true"
            )
            files = []
            for f in metadata["siblings"]:
                if f["rfilename"].endswith(".safetensors"):
                    lfs = f.get("lfs", {})
                    files.append(
                        {
                            "path": f["rfilename"],
                            "sha256": lfs.get("sha256"),
                            "bytes": lfs.get("size", f.get("size")),
                        }
                    )
            assets = []
            for f in metadata["siblings"]:
                if f["rfilename"] in (
                    "config.json",
                    "model.safetensors.index.json",
                    "generation_config.json",
                    "tokenizer.json",
                    "tokenizer_config.json",
                    "vocab.json",
                    "merges.txt",
                    "chat_template.jinja",
                ):
                    assets.append(
                        {
                            "path": f["rfilename"],
                            "bytes": f.get("lfs", {}).get("size", f.get("size")),
                            "sha256": f.get("lfs", {}).get("sha256"),
                            "git_blob_sha1": f.get("blobId"),
                        }
                    )
            if not {"config.json", "tokenizer.json", "tokenizer_config.json"} <= {
                f["path"] for f in assets
            }:
                raise ValueError("Missing tokenizer/config provenance")
            if not files or any(not f["sha256"] or not f["bytes"] for f in files):
                raise ValueError("Missing weight hashes/sizes")
            if len(files) > 1 and 'model.safetensors.index.json' not in {
                asset['path'] for asset in assets
            }:
                raise ValueError('Missing sharded checkpoint index provenance')
            row.update(
                revision=metadata["sha"],
                files=files,
                assets=assets,
                weight_bytes=sum(f["bytes"] for f in files),
                license=metadata.get("cardData", {}).get("license"),
                status="locked",
            )
        except Exception as exc:
            row.update(status="unavailable", error_type=type(exc).__name__)
        models.append(row)
    result = {
        "models": models,
        "generation": cfg["generation"],
        "adapter_scope": "reply-only",
        "purpose": "model-preparation-no-weight-download",
        "human_reviewed": False,
    }
    write_json(output / "models.lock.json", result)
    return result


def local_model(entry):
    p = WORKSPACE / "models" / entry["local_name"]
    if entry.get("status") != "locked":
        raise ValueError("Model revision is not locked")
    if not p.is_dir():
        raise ValueError("Weights not downloaded: " + entry["local_name"])
    for f in entry["files"]:
        file = p / f["path"]
        if not file.resolve().is_relative_to(p.resolve()):
            raise ValueError("Invalid model weight path")
        if (
            not file.is_file()
            or file.stat().st_size != f["bytes"]
            or sha(file) != f["sha256"]
        ):
            raise ValueError("Missing or mismatched model weight: " + f["path"])
    if not entry.get("assets"):
        raise ValueError("Re-lock model with tokenizer/config hashes")
    for asset in entry["assets"]:
        file = p / asset["path"]
        if (
            not file.resolve().is_relative_to(p.resolve())
            or not file.is_file()
            or file.stat().st_size != asset["bytes"]
        ):
            raise ValueError("Missing model asset")
        if asset.get("sha256"):
            good = sha(file) == asset["sha256"]
        else:
            raw = file.read_bytes()
            good = (
                hashlib.sha1(
                    b"blob " + str(len(raw)).encode() + b"\0" + raw
                ).hexdigest()
                == asset["git_blob_sha1"]
            )
        if not good:
            raise ValueError("Tokenizer/config revision mismatch: " + asset["path"])
    return p


def download_model(lock_path, name):
    lock = json.loads(Path(lock_path).read_text())
    validate_settings(lock["generation"])
    entry = next(m for m in lock["models"] if m["name"] == name)
    if entry["status"] != "locked":
        raise ValueError("Cannot download an unlocked model")
    from huggingface_hub import snapshot_download

    target = WORKSPACE / "models" / entry["local_name"]
    snapshot_download(
        entry["repo"],
        revision=entry["revision"],
        local_dir=target,
        cache_dir=WORKSPACE / "hf-cache",
        allow_patterns=[
            "*.json",
            "*.safetensors",
            "*.txt",
            "*.model",
            "*.jinja",
            "LICENSE",
            "README.md",
        ],
        max_workers=2,
    )
    local_model(entry)
    write_json(target / "style-lab-revision.json", entry)
    return {"model": name, "revision": entry["revision"], "verified": True}


class ReplyScopedModel:
    available = True

    def __init__(self, backend, *, arm):
        if arm not in ARMS:
            raise ValueError("Unknown ablation arm")
        self.backend = backend
        self.arm = arm
        self.calls = []

    def chat(self, messages, temperature=0, max_tokens=512):
        return self._call(messages, "reply")

    def chat_analysis(self, messages, temperature=0):
        return self._call(messages, "analysis")

    def _call(self, messages, kind):
        messages = json.loads(canonical(messages))
        if kind == "reply" and self.arm != "base":
            messages[0]["content"] += "\n" + STYLE_HINT
        adapter = kind == "reply" and self.arm == "style_lora"
        row = {
            "kind": kind,
            "adapter_enabled": adapter,
            "input_sha256": hashlib.sha256(canonical(messages).encode()).hexdigest(),
        }
        self.calls.append(row)
        try:
            row.update(self.backend.generate(messages, kind, adapter))
            if not isinstance(row["reply"], str) or not row["reply"].strip():
                raise ValueError("Empty generation")
            return row["reply"]
        except Exception as exc:
            row["error"] = type(exc).__name__
            raise


class SmokeBackend:
    """Offline plumbing fixture, not model output or semantic evaluation."""

    def generate(self, messages, kind, adapter):
        return {
            "reply": (
                '{"emotion":{"valence":0,"arousal":0},"facts":[]}'
                if kind == "analysis"
                else "离线流程占位回复；不是模型效果。"
            ),
            "adapter_enabled": adapter,
            "seconds": 0.0,
            "new_tokens": 0,
            "truncated": False,
            "fixture": True,
        }


class TransformersBackend:
    def __init__(self, path, settings, *, adapter=None, gpu_count=1):
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM

        self.torch = torch
        self.settings = settings
        torch.manual_seed(settings["seed"])
        self.tokenizer = AutoTokenizer.from_pretrained(path, local_files_only=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            path,
            local_files_only=True,
            dtype=torch.bfloat16,
            attn_implementation="sdpa",
            device_map="balanced" if gpu_count > 1 else {"": 0},
            max_memory={i: "36GiB" for i in range(gpu_count)},
        )
        if any(
            str(d) in ("cpu", "disk")
            for d in getattr(self.model, "hf_device_map", {}).values()
        ):
            raise ValueError("CPU/disk offload is forbidden in this comparison")
        if adapter:
            from peft import PeftModel

            self.model = PeftModel.from_pretrained(
                self.model, adapter, is_trainable=False
            )
        self.has_adapter = adapter is not None
        self.model.eval()
        from lmformatenforcer.integrations.transformers import (
            build_token_enforcer_tokenizer_data,
        )

        self.decoder_data = build_token_enforcer_tokenizer_data(
            self.tokenizer, vocab_size=self.model.config.vocab_size
        )
        for index in range(torch.cuda.device_count()):
            torch.cuda.reset_peak_memory_stats(index)

    def generate(self, messages, kind, adapter):
        from contextlib import nullcontext
        from lmformatenforcer import JsonSchemaParser
        from lmformatenforcer.integrations.transformers import (
            build_transformers_prefix_allowed_tokens_fn,
        )
        from avatar.brain.analysis_protocol import ANALYSIS_RESPONSE_FORMAT

        torch = self.torch
        limit = self.settings[
            "analysis_tokens" if kind == "analysis" else "reply_tokens"
        ]
        if adapter and not self.has_adapter:
            raise ValueError("Style arm requires a verified adapter")
        # Peft's context manager restores adapter state even after generation errors.
        scope = (
            self.model.disable_adapter()
            if self.has_adapter and not adapter
            else nullcontext()
        )
        with scope, torch.inference_mode():
            ids = self.tokenizer.apply_chat_template(
                messages,
                tokenize=True,
                add_generation_prompt=True,
                enable_thinking=False,
                return_tensors="pt",
            ).to(self.model.get_input_embeddings().weight.device)
            if ids.shape[1] + limit > self.settings["context_tokens"]:
                raise ValueError("Context exceeds fixed experiment budget")
            options = {}
            if kind == "analysis":
                schema = ANALYSIS_RESPONSE_FORMAT["json_schema"]["schema"]
                options["prefix_allowed_tokens_fn"] = (
                    build_transformers_prefix_allowed_tokens_fn(
                        self.decoder_data, JsonSchemaParser(schema)
                    )
                )
            torch.cuda.synchronize()
            start = time.perf_counter()
            output = self.model.generate(
                ids,
                attention_mask=torch.ones_like(ids),
                max_new_tokens=limit,
                do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id,
                **options,
            )
            torch.cuda.synchronize()
            seconds = time.perf_counter() - start
            tokens = output[0, ids.shape[1] :]
            eos = self.model.generation_config.eos_token_id
            eos = (
                {eos}
                if isinstance(eos, int)
                else set(eos or [self.tokenizer.eos_token_id])
            )
            return {
                "reply": self.tokenizer.decode(tokens, skip_special_tokens=True),
                "adapter_enabled": adapter,
                "seconds": seconds,
                "new_tokens": len(tokens),
                "truncated": len(tokens) == limit and int(tokens[-1]) not in eos,
                "peak_allocated_bytes": [
                    torch.cuda.max_memory_allocated(i)
                    for i in range(torch.cuda.device_count())
                ],
            }


class Fallbacks(logging.Handler):
    def __init__(self):
        super().__init__()
        self.events = []

    def emit(self, record):
        if record.msg in ("认知分析失败，回退规则分析", "模型回复失败，使用规则回复"):
            self.events.append(record.msg)


def run_raw_case(case, backend):
    """Raw model has only minimal identity and transcript; no Avatar state or analysis."""
    from avatar.config import config
    model = ReplyScopedModel(backend, arm="base")
    messages = [{"role": "system", "content": f"你是{config.avatar_name}，{config.avatar_persona}。"}]
    turns = []
    for text in case['turns']:
        messages.append({'role': 'user', 'content': text})
        before = len(model.calls)
        started = time.perf_counter()
        try:
            reply = model.chat(messages)
            item = {'user': text, 'reply': reply}
            messages.append({'role': 'assistant', 'content': reply})
        except Exception as exc:
            item = {'user': text, 'reply': '', 'error': type(exc).__name__}
        calls = model.calls[before:]
        item.update(wall_seconds=time.perf_counter()-started, calls=calls,
                    analysis_fallback=False, reply_fallback=False,
                    truncated=any(c.get('truncated', False) for c in calls))
        turns.append(item)
        if item.get('error'):break
    return {'id': case['id'], 'turns': turns,
            'unavailable_backend_action': case.get('before_last_action')}


def run_suite(suite, backend, output, *, arms=("base",)):
    from avatar.main import Avatar
    from avatar.brain.emotion import EmotionEngine

    results = {}
    assessments = {}
    output = Path(output)
    for arm in arms:
        if arm == 'raw_base':
            rows, scores = [], []
            for case in suite['cases']:
                row = run_raw_case(case, backend)
                rows.append(row)
                # Backend route IDs are inapplicable to a model with no router.
                raw_case = {k:v for k,v in case.items() if k != 'expected_routes'}
                score = assess(raw_case, row['turns'])
                score['backend_route_checks'] = 'not_applicable'
                scores.append(score)
                write_json(output / 'results.partial.json', {**results, arm: rows})
            results[arm], assessments[arm] = rows, scores
            continue
        arm_results = []
        scores = []
        for case in suite["cases"]:
            if case.get("before_last_action") not in (None, "forget_name"):
                raise ValueError("Unsupported case action")
            model = ReplyScopedModel(backend, arm=arm)
            with tempfile.TemporaryDirectory(
                prefix="lab-case-", dir=WORKSPACE / "runtime/tmp"
            ) as folder:
                avatar = Avatar(
                    db_path=str(Path(folder) / "memory.db"),
                    llm=model,
                    session_id=case["id"],
                    embedder=None,
                )
                clock = [0.0]
                avatar.emotion = EmotionEngine(clock=lambda: clock[0])
                turns = []
                try:
                    for i, text in enumerate(case["turns"]):
                        clock[0] = 10 * (i + 1)
                        if (
                            i == len(case["turns"]) - 1
                            and case.get("before_last_action") == "forget_name"
                        ):
                            for row in avatar.list_memories():
                                if row.get("profile_key") == "名字":
                                    avatar.forget_memory(row["id"])
                        trace = Fallbacks()
                        logger = logging.getLogger("avatar.main")
                        logger.addHandler(trace)
                        before = len(model.calls)
                        turn_started = time.perf_counter()
                        try:
                            result = avatar.respond(text, use_tts=False, use_web=False)
                            item = {
                                "user": text,
                                "reply": result["reply"],
                                "result": result,
                                "memories": avatar.list_memories(include_history=True),
                            }
                        except Exception as exc:
                            item = {
                                "user": text,
                                "reply": "",
                                "error": type(exc).__name__,
                            }
                        finally:
                            logger.removeHandler(trace)
                        calls = model.calls[before:]
                        item.update(
                            wall_seconds=time.perf_counter() - turn_started,
                            calls=calls,
                            analysis_fallback="认知分析失败，回退规则分析"
                            in trace.events,
                            reply_fallback="模型回复失败，使用规则回复" in trace.events,
                            truncated=any(c.get("truncated", False) for c in calls),
                        )
                        turns.append(item)
                        if item.get("error"):
                            break
                finally:
                    avatar.memory.close()
            arm_results.append({"id": case["id"], "turns": turns})
            scores.append(assess(case, turns))
            write_json(output / "results.partial.json", {**results, arm: arm_results})
        results[arm] = arm_results
        assessments[arm] = scores
    write_json(output / "results.json", results)
    write_json(output / "checks.json", assessments)
    write_json(output / "comparison.json", compare_reports(assessments))
    return results


def evaluate(
    suite_path,
    output,
    *,
    lock_path=None,
    model_name=None,
    gpus=(),
    adapter=None,
    smoke=False,
    style=False,
    include_raw=False,
):
    suite = json.loads(Path(suite_path).read_text())
    if not suite.get("cases") or len({c["id"] for c in suite["cases"]}) != len(
        suite["cases"]
    ):
        raise ValueError("Invalid or duplicate suite IDs")
    if any(not c.get("turns") or not c.get("checks") for c in suite["cases"]):
        raise ValueError("Incomplete suite")
    if not smoke and any(c.get("fixture") for c in suite["cases"]):
        raise ValueError("Fixture cannot be used as real evaluation")
    output = new_output(output)
    from avatar.config import config

    config.embedding.model = ""
    config.llm.api_key = ""
    config.avatar_name = "小海"
    config.avatar_persona = "一个温柔又有点好奇心的AI伙伴"
    arms = ARMS if style else ("base",)
    if include_raw:
        arms = ("raw_base",) + tuple(arms)
    manifest = {
        "kind": "offline-fixture" if smoke else "real-local-model",
        "suite_sha256": sha(suite_path),
        "backend": source_state(),
        "arms": arms,
        "raw_base_definition": "minimal identity + full transcript; no Avatar analysis, memory, guard or adapter" if include_raw else None,
        "raw_route_checks": "not_applicable" if include_raw else None,
        "raw_forget_action": "not available; original transcript retained" if include_raw else None,
        "style_hint": STYLE_HINT,
        "analysis_adapter": False,
        "fresh_state_per_case": True,
        "web_tts_embeddings": False,
        "human_reviewed": False,
        "semantic_quality": "unscored",
        "case_ids": [c["id"] for c in suite["cases"]],
    }
    if smoke:
        manifest["generation"] = {"fixture": True}
        write_json(output / "manifest.json", manifest)
        return run_suite(suite, SmokeBackend(), output, arms=arms)
    if not lock_path or not model_name:
        raise ValueError("Real run requires model lock and name")
    lock = json.loads(Path(lock_path).read_text())
    validate_settings(lock["generation"])
    entry = next(m for m in lock["models"] if m["name"] == model_name)
    try:
        validate_gpu_selection(
            list(gpus), gpu_inventory(), required_cards=entry["gpus"]
        )
        path = local_model(entry)
    except Exception as exc:
        write_json(
            output / "blocked.json",
            {
                "status": "blocked",
                "reason": str(exc),
                "model": model_name,
                "no_model_loaded": True,
            },
        )
        raise
    if style:
        if not adapter:
            raise ValueError("Real style comparison requires adapter")
        proof = json.loads((Path(adapter).parent / "manifest.json").read_text())
        if (
            proof.get("status") != "completed"
            or proof["base_model_id"] != entry["repo"]
            or proof["base_revision"] != entry["revision"]
            or sha(Path(adapter) / "adapter_model.safetensors")
            != proof["adapter_sha256"]
        ):
            raise ValueError("Adapter base/hash mismatch")
        if sha(Path(adapter) / "adapter_config.json") != proof[
            "adapter_config_sha256"
        ] or not json.loads(
            (Path(adapter).parent / "reload-verification.json").read_text()
        ).get(
            "passed"
        ):
            raise ValueError(
                "Adapter config or fresh-process reload verification missing"
            )
        manifest["adapter_manifest_sha256"] = sha(
            Path(adapter).parent / "manifest.json"
        )
    with gpu_lease(list(gpus), entry["gpus"]):
        manifest.update(model=entry, generation=lock["generation"], physical_gpus=gpus)
        write_json(output / "manifest.json", manifest)
        backend = TransformersBackend(
            path, lock["generation"], adapter=adapter, gpu_count=len(gpus)
        )
        return run_suite(suite, backend, output, arms=arms)


def compare_runs(paths, output):
    manifests = []
    arms = {}
    reference = None
    for path in paths:
        path = Path(path)
        manifest = json.loads((path / "manifest.json").read_text())
        signature = {
            k: manifest[k]
            for k in (
                "kind",
                "suite_sha256",
                "generation",
                "fresh_state_per_case",
                "web_tts_embeddings",
            )
        }
        signature["backend_files"] = manifest["backend"]["files"]
        if reference is not None and signature != reference:
            raise ValueError(
                "Runs differ in suite, backend, generation settings or real/fixture mode"
            )
        reference = signature
        checks = json.loads((path / "checks.json").read_text())
        for arm, rows in checks.items():
            if {r["id"] for r in rows} != set(manifest["case_ids"]):
                raise ValueError("Incomplete run")
            name = (
                manifest.get("model", {}).get("name", f"fixture-{len(manifests)}")
                + ":"
                + arm
            )
            if name in arms:
                raise ValueError("Duplicate model/arm run")
            arms[name] = rows
        manifests.append(
            {
                "path": str(path.resolve()),
                "manifest_sha256": sha(path / "manifest.json"),
                "checks_sha256": sha(path / "checks.json"),
            }
        )
    if not manifests:
        raise ValueError("No runs")
    result = compare_reports(arms) | {"sources": manifests, "kind": reference["kind"]}
    output = new_output(output)
    write_json(output / "comparison.json", result)
    return result
