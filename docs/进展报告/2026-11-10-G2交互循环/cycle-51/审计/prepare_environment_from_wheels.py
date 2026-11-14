"""Restore the same training environment from fully verified wheels after v3 retires."""
from email.parser import BytesParser
import json
import os
from pathlib import Path
import subprocess
import time

from packaging.requirements import Requirement
from avatar.lab.common import sha
from prepare_training_environment import inventory

ROOT = Path(__file__).resolve().parents[5]
BASE = Path(__file__).resolve().parents[1]
PREPARATION = BASE / "审计/工作目录/003-环境与基础权重"
WORK = PREPARATION / "environment-v4"
CACHE = BASE / "审计/工作目录/008-CUDA完整依赖缓存"
ASSETS = Path("/data/Users/zrh/data/hhu-ai-avatar")
TARGET = ASSETS / "envs/hhu-ai-avatar-train"


def main():
    assert subprocess.run(["mountpoint", "-q", "/data"]).returncode == 0
    protocol_path = PREPARATION / "local-wheel-recovery-protocol-v1.json"
    protocol = json.loads(protocol_path.read_text())
    cache = json.loads((CACHE / "wheel-cache-v1.json").read_text())
    registry = json.loads((CACHE / "wheel-registry-v2.json").read_text())
    if cache["status"] != "complete" or len(cache["artifacts"]) != 15:
        raise ValueError("C51 complete verified wheel cache required for local recovery")
    assert len(registry["artifacts"]) == 15
    assert cache["registry_sha256"] == sha(CACHE / "wheel-registry-v2.json")
    independent = json.loads((CACHE / "wheel-cache-independent-v1.json").read_text())
    assert independent["verified"] and independent["wheel_count"] == 15
    assert independent["cache_run_sha256"] == sha(CACHE / "wheel-cache-v1.json")
    assert independent["registry_sha256"] == sha(CACHE / "wheel-registry-v2.json")
    previous = json.loads((PREPARATION / "environment-v3/environment-v3.json").read_text())
    assert previous["status"] == "failed" and previous["target"] == str(TARGET)
    retirement_path = PREPARATION / "environment-v3/operator-retirement-v1.json"
    retirement = json.loads(retirement_path.read_text())
    assert retirement["verified"] and retirement["parent_process_retired"] and retirement["child_process_retired"]
    for pid in (retirement["parent_pid"], retirement["child_pid"]):
        assert not Path(f"/proc/{pid}").exists()
    for path in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            args = path.read_bytes().decode().split("\0")[:-1]
        except (OSError, UnicodeDecodeError):
            continue
        assert not (args and args[0] == str(TARGET / "bin/python") and "pip" in args and "install" in args)
    env = dict(os.environ, CUDA_VISIBLE_DEVICES="", PYTHONDONTWRITEBYTECODE="1",
        TMPDIR=str(ASSETS / "tmp"), PIP_CACHE_DIR=str(ASSETS / "cache/pip"),
        XDG_CACHE_HOME=str(ASSETS / "cache/xdg"), HF_HOME=str(ASSETS / "cache/huggingface"))
    originals = {name: inventory(ASSETS / "envs" / name / "bin/python", env)
        for name in previous["original_environments_before"]}
    assert originals == previous["original_environments_before"]
    seed = inventory(TARGET / "bin/python", env)
    assert seed["local_versions"] == {"pip": "25.3", "setuptools": "59.6.0"}
    wheels = []
    for spec in registry["artifacts"]:
        proof = json.loads((CACHE / "completed-wheels-v1" / (spec["package"] + ".json")).read_text())
        path = Path(proof["wheel"])
        assert path.resolve().is_relative_to((ASSETS / "cache/wheelhouse/c51-cu124-v1").resolve())
        assert proof["verified"] and path.stat().st_size == spec["bytes"] and sha(path) == spec["sha256"]
        wheels.append(str(path))
    WORK.mkdir(exist_ok=False)
    output = WORK / "environment-v4.json"
    result = {"status": "running", "target": str(TARGET), "original_environments_before": originals,
        "seed": seed, "steps": [], "recovery_protocol_sha256": sha(protocol_path),
        "prior_retirement_sha256": sha(retirement_path), "wheel_cache_sha256": sha(CACHE / "wheel-cache-v1.json"),
        "model_constructions": 0, "CUDA_allocation": False, "training_steps": 0}
    def save():
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    def run(name, argv):
        log = WORK / (name + ".log")
        began = time.perf_counter()
        with log.open("x") as stream:
            command = subprocess.run(argv, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT)
        result["steps"].append({"name": name, "argv": argv, "returncode": command.returncode,
            "seconds": time.perf_counter() - began})
        save()
        if command.returncode:
            raise RuntimeError(name + " failed; keep logs and partial target")
        print(name, "complete", flush=True)
    save()
    try:
        python = str(TARGET / "bin/python")
        run("local-torch-CUDA-install", [python, "-m", "pip", "--isolated", "install", "--no-index", "--no-deps",
            "--report", str(WORK / "torch-local-pip-report.json"), *wheels])
        metadata = BytesParser().parsebytes((CACHE / "metadata-v2/torch-wheel-v1.metadata.txt").read_bytes())
        pure = []
        for value in metadata.get_all("Requires-Dist"):
            requirement = Requirement(value)
            if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
                continue
            if not requirement.name.startswith("nvidia-") and requirement.name != "triton":
                pure.append(str(requirement))
        pure_path = WORK / "torch-pure-dependencies-v1.txt"
        pure_path.write_text("\n".join(pure) + "\n")
        constraints = WORK / "constraints-v1.txt"
        constraints.write_text("".join(key + "==" + value + "\n" for key, value in protocol["constraints"].items()))
        run("training-and-torch-pure-install", [python, "-m", "pip", "--isolated", "install",
            "--index-url", "https://pypi.org/simple", "--cache-dir", str(ASSETS / "cache/pip"),
            "--timeout", "60", "--retries", "3", "--progress-bar", "off",
            "--report", str(WORK / "training-pip-report.json"), "-c", str(constraints),
            "-r", str(pure_path), "-r", str(ROOT / "training/requirements-eval.txt"),
            "-r", str(ROOT / "requirements.txt")])
        run("environment-pip-check", [python, "-m", "pip", "check"])
        run("environment-pip-freeze", [python, "-m", "pip", "freeze", "--all"])
        code = '''import json,sys,torch,transformers,peft,lmformatenforcer,interegular
from transformers import Qwen3ForCausalLM,AutoTokenizer
print(json.dumps({'prefix':sys.prefix,'torch':torch.__version__,'CUDA_build':torch.version.cuda,'CUDA_initialized':torch.cuda.is_initialized(),'torch_cuda_visible_count':torch.cuda.device_count(),'Qwen3_class':Qwen3ForCausalLM.__name__,'CPU_imports_passed':True}))
'''
        actual = json.loads(subprocess.check_output([python, "-B", "-c", code], cwd=ROOT, env=env, text=True))
        assert actual["torch"] == "2.6.0+cu124" and actual["CUDA_initialized"] is False and actual["torch_cuda_visible_count"] == 0
        result["CPU_import_probe"] = actual
        result["installed"] = inventory(TARGET / "bin/python", env)
        result["original_environments_after"] = {name: inventory(ASSETS / "envs" / name / "bin/python", env) for name in originals}
        assert result["original_environments_after"] == originals
        result.update(status="complete", existing_environments_unchanged=True)
    except BaseException as error:
        result.update(status="failed", error=type(error).__name__ + ": " + str(error))
        save()
        raise
    save()
    print("C51 wheel recovery complete;fixed packages,pip check,CPU imports,original envs unchanged;0 model/GPU/training")


if __name__ == "__main__":
    main()
