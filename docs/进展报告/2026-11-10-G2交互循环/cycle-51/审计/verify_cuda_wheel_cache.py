"""Independently reread all fifteen complete wheels before any installer retirement."""
from email.parser import BytesParser
import json
from pathlib import Path
import subprocess
import zipfile

from packaging.utils import canonicalize_name
from packaging.version import Version
from avatar.lab.common import sha

ROOT = Path(__file__).resolve().parents[5]
WORK = Path(__file__).parent / "工作目录/008-CUDA完整依赖缓存"
ASSETS = Path("/data/Users/zrh/data/hhu-ai-avatar")


def main():
    output = WORK / "wheel-cache-independent-v1.json"
    if output.exists():
        raise ValueError("independent wheel cache proof already exists")
    cache_path = WORK / "wheel-cache-v1.json"
    cache_sha_before = sha(cache_path)
    cache = json.loads(cache_path.read_text())
    if cache["status"] != "complete":
        raise ValueError("complete fifteen-wheel cache required before independent admission")
    registry_path = WORK / "wheel-registry-v2.json"
    registry = json.loads(registry_path.read_text())
    assert cache["registry_sha256"] == sha(registry_path)
    assert len(registry["artifacts"]) == len(cache["artifacts"]) == 15
    assert cache["source_sha256"] == sha(Path(__file__).with_name("cache_cuda_wheels.py"))
    indexed = {f["package"]: f for f in cache["artifacts"]}
    assert len(indexed) == 15
    verified = []
    for spec in registry["artifacts"]:
        receipt_path = WORK / "completed-wheels-v1" / (spec["package"] + ".json")
        assert sha(receipt_path) == indexed[spec["package"]]["proof_sha256"]
        receipt = json.loads(receipt_path.read_text())
        path = Path(receipt["wheel"])
        assert path.resolve().is_relative_to((ASSETS / "cache/wheelhouse/c51-cu124-v1").resolve())
        before = path.stat()
        assert before.st_size == spec["bytes"] and sha(path) == spec["sha256"]
        with zipfile.ZipFile(path) as archive:
            names = [n for n in archive.namelist() if n.endswith(".dist-info/METADATA")]
            assert len(names) == 1
            raw = archive.read(names[0])
        metadata = BytesParser().parsebytes(raw)
        assert canonicalize_name(metadata["Name"]) == canonicalize_name(spec["package"])
        assert Version(metadata["Version"]) == Version(spec["version"])
        assert before.st_size == path.stat().st_size and before.st_mtime_ns == path.stat().st_mtime_ns
        verified.append({"package": spec["package"], "version": spec["version"], "path": str(path),
            "bytes": spec["bytes"], "sha256": spec["sha256"], "closed_receipt_sha256": sha(receipt_path)})
    assert sha(cache_path) == cache_sha_before
    proof = {"verified": True, "scope": "independent complete wheel SHA/ZIP metadata only, no installed runtime or CUDA approval",
        "wheel_count": 15, "total_bytes": sum(f["bytes"] for f in verified), "files": verified,
        "cache_run_sha256": sha(cache_path), "registry_sha256": sha(registry_path),
        "verifier_sha256": sha(Path(__file__)), "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "environment_mutated": False, "model_constructions": 0, "GPU_allocations": 0, "training_steps": 0}
    with output.open("x") as stream:
        json.dump(proof, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print("C51 independent wheel cache:15 complete SHA/ZIP metadata identities;bytes", proof["total_bytes"], ";no install/model/GPU")


if __name__ == "__main__":
    main()
