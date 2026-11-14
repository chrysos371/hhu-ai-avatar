"""Normal CLI negative controls while real setup/cache are authoritatively unready."""
import json
import os
from pathlib import Path
import subprocess
import sys

from avatar.lab.common import sha
from environment_receipt import ROOT, PREPARATION, ADMISSION


def main():
    work = Path(__file__).parent / "工作目录/009-独立环境准入"
    output = work / "unready-cli-v1.json"
    assert not output.exists() and not ADMISSION.exists()
    cache = Path(__file__).parent / "工作目录/008-CUDA完整依赖缓存/wheel-cache-v1.json"
    source = PREPARATION / "environment-v3/environment-v3.json"
    assert json.loads(cache.read_text())["status"] != "complete"
    assert json.loads(source.read_text())["status"] != "complete"
    assert not (PREPARATION / "environment-v4").exists()
    proc = Path("/proc/407654")
    assert proc.exists() and (proc / "cmdline").read_bytes().split(b"\0")[-2].endswith(b"prepare_training_environment.py")
    observed = {"pid": 407654, "start_ticks": (proc / "stat").read_text().split()[21],
        "command": (proc / "cmdline").read_bytes().decode().split("\0")[:-1]}
    work.mkdir(exist_ok=True)
    cases = [("verify_cuda_wheel_cache.py", [], "complete fifteen-wheel cache required before independent admission"),
        ("prepare_environment_from_wheels.py", [], "C51 complete verified wheel cache required for local recovery"),
        ("verify_training_environment.py", ["--preparation-source", "environment-v3/environment-v3.json"],
            "environment preparation is not complete")]
    results = []
    for name, arguments, reason in cases:
        script = Path(__file__).with_name(name)
        argv = [sys.executable, "-B", str(script), *arguments]
        actual = subprocess.run(argv, cwd=ROOT, env=dict(os.environ, CUDA_VISIBLE_DEVICES=""),
            text=True, capture_output=True)
        assert actual.returncode == 1 and "ValueError: " + reason in actual.stderr
        assert "ModuleNotFoundError" not in actual.stderr
        results.append({"argv": argv, "returncode": actual.returncode, "expected_reason": reason,
            "stdout": actual.stdout, "stderr": actual.stderr, "script_sha256": sha(script)})
    assert not ADMISSION.exists() and not (PREPARATION / "environment-v4").exists()
    proof = {"passed": True, "scope": "three normal CLI calls reject actual unfinished preparation/cache for precise reasons; no positive environment admission",
        "actual_CLI_controls": results, "setup_process_at_observation_only": observed,
        "reader_sha256": sha(Path(__file__).with_name("environment_receipt.py")), "verifier_sha256": sha(Path(__file__)),
        "admission_created": False, "replacement_install_created": False,
        "model_constructions": 0, "GPU_allocations": 0, "training_steps": 0,
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()}
    with output.open("x") as stream:
        json.dump(proof, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print("C51 preparation admission:3 normal CLI exact unready rejections;no admission/replacement install/model/GPU")


if __name__ == "__main__":
    main()
