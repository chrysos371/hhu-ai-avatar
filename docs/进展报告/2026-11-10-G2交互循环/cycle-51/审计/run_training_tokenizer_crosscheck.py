"""After training-env completion, compare actual production tokens on CPU."""
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys

from avatar.lab.common import sha
from avatar.lab.training import preflight

ROOT = Path(__file__).resolve().parents[5]
BASE = Path(__file__).resolve().parents[1]
ASSETS = Path("/data/Users/zrh/data/hhu-ai-avatar")
WORK = BASE / "审计/工作目录/005-真实分词预检"


def main():
    assert os.environ.get("CUDA_VISIBLE_DEVICES") == ""
    assert sys.prefix == str(ASSETS / "envs/hhu-ai-avatar-train")
    environment = json.loads((BASE / "审计/工作目录/003-环境与基础权重/environment-v3/environment-v3.json").read_text())
    assert environment["status"] == "complete" and environment["existing_environments_unchanged"]
    proof_path = WORK / "training-tokenizer-crosscheck-v1.json"
    assert not proof_path.exists()
    previous = json.loads((WORK / "mask-preflight-v1.json").read_text())
    assert previous["verified"] and previous["all_prompt_and_history_tokens_masked"]
    assert sha(ROOT / "src/avatar/lab/training.py") == previous["training_module_sha256"]
    packages = ("transformers", "tokenizers", "huggingface_hub", "safetensors", "numpy", "Jinja2")
    versions = {name: importlib.metadata.version(name) for name in packages}
    assert all(versions[name] == previous["versions"][name] for name in packages)
    protocol = json.loads((WORK / "tokenizer-protocol.json").read_text())
    config = WORK / "training-config-v1.json"
    data = Path(protocol["data"])
    assert sha(config) == previous["config_sha256"]
    assert sha(data.with_name("manifest.json")) == previous["data_manifest_sha256"]
    assets = json.loads((BASE / "审计/工作目录/003-环境与基础权重/tokenizer-assets-v1.json").read_text())
    assert all(sha(Path(f["path"])) == f["sha256"] for f in assets["files"])
    import torch
    assert not torch.cuda.is_initialized() and torch.cuda.device_count() == 0
    output = ASSETS / "artifacts/c51/training-tokenizer-crosscheck-v1"
    assert not output.exists()
    result = preflight(data, Path(protocol["model_assets"]), output, config)
    assert (result["samples"], result["dev_samples"], result["rejected"]) == (176, 44, [])
    assert sha(output / "tokens.json") == previous["tokens_sha256"]
    assert not torch.cuda.is_initialized()
    proof = {"verified": True, "scope": "training-env CPU tokenization equals independently verified tokenizer-only output; not CUDA/model training",
        "tokenizer_preflight_proof_sha256": sha(WORK / "mask-preflight-v1.json"),
        "training_environment_proof_sha256": sha(BASE / "审计/工作目录/003-环境与基础权重/environment-v3/environment-v3.json"),
        "verifier_sha256": sha(Path(__file__)), "config_sha256": sha(config),
        "environment": sys.prefix, "versions": versions, "torch": torch.__version__,
        "tokens_sha256": sha(output / "tokens.json"), "identical_to_tokenizer_only_environment": True,
        "preflight_report_sha256": sha(output / "preflight.json"), "external_output": str(output),
        "train_samples": 176, "dev_samples": 44, "rejected": 0,
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "model_constructions": 0, "training_steps": 0, "CUDA_initialized": False,
        "full_base_admission_separate": True, "real_training_admitted": False}
    proof_path.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n")
    print("C51 training-env tokenizer crosscheck:176/44 identical token/mask bytes;0 model/CUDA/training")


if __name__ == "__main__":
    main()
