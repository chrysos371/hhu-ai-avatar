"""Exact official wheel cache with whole-file SHA; original installer is untouched."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from email.parser import BytesParser
import hashlib
import json
import math
import os
from pathlib import Path
import time
import urllib.request
import zipfile

from packaging.utils import canonicalize_name
from packaging.version import Version

WORK = Path(__file__).parent / "工作目录/008-CUDA完整依赖缓存"
ASSETS = Path("/data/Users/zrh/data/hhu-ai-avatar")


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write(path, value):
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def main():
    protocol_path = WORK / "registry-protocol-v1.json"
    protocol = json.loads(protocol_path.read_text())
    registry_path = WORK / "wheel-registry-v2.json"
    registry = json.loads(registry_path.read_text())
    output = WORK / "wheel-cache-v1.json"
    assert not output.exists()
    wheelhouse = ASSETS / "cache/wheelhouse/c51-cu124-v1"
    wheelhouse.mkdir(parents=True, exist_ok=False)
    completed = WORK / "completed-wheels-v1"
    completed.mkdir(exist_ok=False)
    result = {"status": "running", "scope": "independent identical wheel cache only, no install",
        "registry_sha256": sha(registry_path), "protocol_sha256": sha(protocol_path),
        "source_sha256": sha(Path(__file__)), "wheelhouse": str(wheelhouse), "artifacts": [],
        "original_transfers_not_stopped_by_this_helper": True, "environment_mutated": False,
        "model_constructions": 0, "GPU_allocations": 0, "training_steps": 0}
    write(output, result)
    def verify(path, spec):
        assert path.stat().st_size == spec["bytes"] and sha(path) == spec["sha256"]
        with zipfile.ZipFile(path) as archive:
            names = [n for n in archive.namelist() if n.endswith(".dist-info/METADATA")]
            assert len(names) == 1
            raw = archive.read(names[0])
            metadata = BytesParser().parsebytes(raw)
        assert canonicalize_name(metadata["Name"]) == canonicalize_name(spec["package"])
        assert Version(metadata["Version"]) == Version(spec["version"])
        if spec["package"] == "torch":
            assert hashlib.sha256(raw).hexdigest() == registry["official_torch_metadata_sha256"]
    def cache(spec):
        began = time.perf_counter()
        destination = wheelhouse / spec["filename"]
        # Completed original pip artifacts are only read/linked, never overwritten or deleted.
        for path in sorted((ASSETS / "tmp").glob("pip-unpack-*/" + spec["filename"])):
            if path.stat().st_size != spec["bytes"]:
                continue
            verify(path, spec)
            os.link(path, destination)
            return {"source_mode": "existing_complete_pip_wheel", "original": str(path),
                "seconds_including_proof": time.perf_counter() - began}
        folder = ASSETS / "cache/cuda-wheel-ranges/c51-v1" / spec["sha256"]
        folder.mkdir(parents=True, exist_ok=False)
        size, chunk = spec["bytes"], protocol["future_chunk_bytes"]
        count = math.ceil(size / chunk)
        def part(index):
            start, end = index * chunk, min(size, (index + 1) * chunk) - 1
            expected = end - start + 1
            path = folder / f"chunk-{index:04}.bin"
            partial = path.with_suffix(".part")
            for attempt in range(protocol["future_attempts_per_chunk"]):
                try:
                    offset = partial.stat().st_size if partial.exists() else 0
                    assert 0 <= offset <= expected
                    if offset < expected:
                        request = urllib.request.Request(spec["url"], headers={"Range": f"bytes={start+offset}-{end}"})
                        with urllib.request.urlopen(request, timeout=protocol["request_timeout_seconds"]) as response:
                            assert response.status == 206 and response.headers["Content-Range"] == f"bytes {start+offset}-{end}/{size}"
                            with partial.open("ab") as stream:
                                while stream.tell() < expected:
                                    raw = response.read(min(65536, expected - stream.tell()))
                                    if not raw:
                                        break
                                    stream.write(raw)
                                    stream.flush()
                            assert partial.stat().st_size == expected
                    partial.replace(path)
                    return index
                except Exception:
                    if attempt + 1 == protocol["future_attempts_per_chunk"]:
                        raise
        finished = 0
        with ThreadPoolExecutor(max_workers=protocol["future_range_workers"]) as pool:
            futures = [pool.submit(part, index) for index in range(count)]
            for future in as_completed(futures):
                future.result()
                finished += 1
                print(spec["package"], "range chunks", finished, "/", count, flush=True)
        joined = folder / "joined.whl"
        with joined.open("xb") as stream:
            for index in range(count):
                with (folder / f"chunk-{index:04}.bin").open("rb") as piece:
                    for raw in iter(lambda: piece.read(8 * 1024 * 1024), b""):
                        stream.write(raw)
        verify(joined, spec)
        os.link(joined, destination)
        return {"source_mode": "registered_exact_range_transfer", "chunks": count,
            "seconds_including_proof": time.perf_counter() - began}
    try:
        for spec in sorted(registry["artifacts"], key=lambda f: f["bytes"]):
            receipt = {**spec, **cache(spec), "verified": True,
                "wheel": str(wheelhouse / spec["filename"]), "installed": False}
            path = completed / (spec["package"] + ".json")
            assert not path.exists()
            write(path, receipt)
            result["artifacts"].append({"package": spec["package"], "proof": str(path), "proof_sha256": sha(path)})
            write(output, result)
            print("closed verified wheel", spec["package"], spec["bytes"], receipt["source_mode"], flush=True)
        assert len(result["artifacts"]) == len(registry["artifacts"]) == 15
        result["status"] = "complete"
    except BaseException as error:
        result.update(status="failed", error=type(error).__name__ + ": " + str(error))
        write(output, result)
        raise
    write(output, result)
    print("C51 exact CUDA wheel cache complete:15 whole SHA/metadata identities;no environment mutation", flush=True)


if __name__ == "__main__":
    main()
