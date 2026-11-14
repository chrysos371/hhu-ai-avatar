"""C52 committed-source and preparation gates, without importing Torch."""
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[5]
BASE = Path(__file__).resolve().parents[1]
C51 = BASE.parent / "cycle-51"
ASSETS = Path("/data/Users/zrh/data/hhu-ai-avatar")
WORK = BASE / "审计/工作目录/003-真实执行输入"
RUN = ASSETS / "artifacts/c52/real-transfer-v1"
PROTOCOL = ROOT / "evals/interaction/cycle-52/correction-transfer-protocol.json"
CASES = ROOT / "evals/interaction/cycle-52/correction-transfer-cases.json"
PREPARATION = C51 / "审计/工作目录/003-环境与基础权重"
TOKENIZATION = C51 / "审计/工作目录/005-真实分词预检"
DATA = ASSETS / "artifacts/c51/correction-data-v1/sft.jsonl"
LOCK = PREPARATION / "model-v1/models.lock.json"
STAGES = ("before", "train", "reload", "after")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def protocol_check():
    p = read(PROTOCOL)
    require(type(p.get("version")) is int and p["version"] == 1, "C52 protocol version differs")
    require(p["cases_sha256"] == sha(CASES), "C52 cases identity changed")
    require(p["default_activation_authorized"] is False and p["protected_partition_authorized"] is False,
        "C52 isolated developmental experiment only")
    require(p["whole_experiment_wallclock_cutoff"] is None, "no whole-stage deadline allowed")
    expected = {"seed": 42, "max_length": 2048, "max_steps": 44, "epochs_cap": 1,
        "gradient_accumulation_steps": 4, "lora_r": 8, "lora_alpha": 16,
        "lora_dropout": 0.05, "target_modules": ["q_proj", "v_proj"],
        "learning_rate": 2e-5, "analysis_adapter_enabled": False,
        "dtype": "bfloat16", "attention": "sdpa"}
    for key, value in expected.items():
        require(type(p["training"].get(key)) is type(value) and p["training"][key] == value,
            "C52 training contract changed: " + key)
    expected = {"cases": 22, "repetitions": 3, "trials_per_phase": 66,
        "generation_cap_per_phase": 134, "two_phase_generation_cap": 268,
        "additional_save_reload_probe_generations": 2,
        "additional_save_reload_probe_direct_forwards": 2,
        "context_tokens": 8192, "reply_tokens": 512, "analysis_tokens": 512,
        "do_sample": False, "enable_thinking": False}
    for key, value in expected.items():
        require(type(p["evaluation"].get(key)) is type(value) and p["evaluation"][key] == value,
            "C52 sampling contract changed: " + key)
    require(len(read(CASES)["cases"]) == 22, "C52 case count differs")
    return p


def preparation_check(expected_seal):
    environment = read(PREPARATION / "environment-v3/environment-v3.json")
    require(environment["status"] == "complete", "C51 training environment is not complete")
    require(environment["existing_environments_unchanged"] is True, "original environments changed")
    base = read(PREPARATION / "model-v1/model-preparation.json")
    require(base["status"] == "complete" and base["shard_index_verified"] is True
        and base["all_git_or_LFS_identities_verified"] is True, "C51 complete base identity missing")
    mask = read(TOKENIZATION / "mask-preflight-v1.json")
    cross = read(TOKENIZATION / "training-tokenizer-crosscheck-v1.json")
    require(mask["verified"] is True and cross["verified"] is True
        and cross["identical_to_tokenizer_only_environment"] is True, "C51 tokenizer crosscheck missing")
    require(mask["tokens_sha256"] == cross["tokens_sha256"], "C51 cross-environment tokens differ")
    seal_path = C51 / "审计/证据清单.json"
    require(type(expected_seal) is str and re.fullmatch("[0-9a-f]{64}", expected_seal) is not None,
        "C51 explicit seal SHA required")
    require(seal_path.is_file() and sha(seal_path) == expected_seal, "C51 preparation seal missing or changed")
    seal = read(seal_path)
    for name in ("审计/系统审计与推进报告.md", "审计/系统审计与推进报告.html"):
        require(name in seal, "C51 final MD/HTML not sealed")
    require(all((C51 / name).resolve().is_relative_to(C51.resolve())
        and sha(C51 / name) == value for name, value in seal.items()), "C51 sealed bytes changed")
    return environment


def required_inputs():
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0")
    names = {n for n in tracked if n.startswith(("src/", "evals/", "training/"))
        or n in ("requirements.txt", "pyproject.toml", "scripts/project_env.sh", "scripts/project-python")}
    names.update(str(p.relative_to(ROOT)) for p in (BASE / "审计").glob("*.py"))
    names.update(str((BASE.parent / "cycle-50/审计" / name).relative_to(ROOT))
        for name in ("sample_history.py", "verify_observations.py", "text_shape.py"))
    names.add(str((C51 / "审计/证据清单.json").relative_to(ROOT)))
    for p in (PREPARATION / "environment-v3/environment-v3.json",
        PREPARATION / "model-v1/model-preparation.json", LOCK,
        TOKENIZATION / "mask-preflight-v1.json", TOKENIZATION / "training-tokenizer-crosscheck-v1.json",
        TOKENIZATION / "training-config-v1.json"):
        names.add(str(p.relative_to(ROOT)))
    return sorted(names)


def historical(ref, names):
    raw = subprocess.check_output(["git", "archive", "--format=tar", ref, "--", *names], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        return {m.name: hashlib.sha256(archive.extractfile(m).read()).hexdigest()
            for m in archive if m.isfile()}


def verify_freeze(path, expected):
    path = Path(path).resolve()
    require(path == (WORK / "freeze-v1.json").resolve(), "C52 registered freeze path required")
    require(type(expected) is str and re.fullmatch("[0-9a-f]{64}", expected) is not None
        and sha(path) == expected, "C52 freeze SHA differs")
    frozen = read(path)
    protocol_check()
    require(frozen["run_root"] == str(RUN) and frozen["stages"] == list(STAGES), "C52 execution sequence differs")
    require(frozen["default_activation_authorized"] is False, "C52 no default activation")
    preparation_check(frozen["c51_seal_sha256"])
    names = required_inputs()
    require(set(names) == set(frozen["sha256"]), "C52 execution input set changed")
    require(all(sha(ROOT / name) == value for name, value in frozen["sha256"].items()),
        "C52 execution source bytes changed")
    require(historical(frozen["source_ref"], names) == frozen["sha256"], "C52 source not committed at freeze")
    for name, value in frozen["external_data_sha256"].items():
        require(sha(DATA.parent / name) == value, "C52 external dataset changed")
    return frozen


def training_binding_files():
    return {"training_manifest_sha256": RUN / "adapter/manifest.json",
        "optimizer_log_sha256": RUN / "adapter/steps.json",
        "adapter_model_sha256": RUN / "adapter/adapter/adapter_model.safetensors",
        "adapter_config_sha256": RUN / "adapter/adapter/adapter_config.json",
        "saved_probe_sha256": RUN / "adapter/probe.pt"}


def verify_training_binding():
    proof = read(RUN / "ledger/train-verified.json")
    require(all(proof[key] == sha(path) for key, path in training_binding_files().items()),
        "previously verified training artifacts changed")
