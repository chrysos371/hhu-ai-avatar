"""Bounded official-index identity and first-MiB transfer probe, no installation."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import html
import json
from pathlib import Path
import re
import time
import urllib.request
from urllib.parse import urlsplit, urldefrag

ROOT = Path(__file__).resolve().parents[5]
WORK = Path(__file__).parent / "工作目录/007-CUDA依赖传输探测"
ASSETS = Path("/data/Users/zrh/data/hhu-ai-avatar")


def main():
    protocol = json.loads((WORK / "probe-protocol-v1.json").read_text())
    output = WORK / "transport-probe-v1.json"
    assert not output.exists()
    raw = []
    for index, url in enumerate(protocol["metadata_sources"]):
        with urllib.request.urlopen(url, timeout=protocol["request_timeout_seconds"]) as response:
            data = response.read(protocol["metadata_max_bytes"] + 1)
        assert len(data) <= protocol["metadata_max_bytes"]
        path = WORK / ("official-pypi-v1.json" if index == 0 else "official-torch-index-v1.html.txt")
        assert not path.exists()
        path.write_bytes(data)
        raw.append(data)
    artifact = next(f for f in json.loads(raw[0])["urls"] if f["filename"] == protocol["filename"])
    links = [html.unescape(v) for v in re.findall(r'href="([^"]+)"', raw[1].decode())
        if protocol["filename"] in v]
    assert len(links) == 1
    nvidia, fragment = urldefrag(links[0])
    expected = artifact["digests"]["sha256"]
    assert fragment == "sha256=" + expected
    urls = {"pytorch_index_nvidia": nvidia, "official_pypi": artifact["url"]}
    assert urlsplit(nvidia).hostname == "pypi.nvidia.com"
    assert urlsplit(artifact["url"]).hostname == "files.pythonhosted.org"
    folder = ASSETS / "cache/cuda-wheel-probes/c51-v1"
    folder.mkdir(parents=True, exist_ok=False)
    def probe(item):
        name, url = item
        start = time.perf_counter()
        request = urllib.request.Request(url, headers={"Range": f'bytes=0-{protocol["probe_bytes"]-1}'})
        try:
            with urllib.request.urlopen(request, timeout=protocol["request_timeout_seconds"]) as response:
                body = response.read(protocol["probe_bytes"] + 1)
                observed = {"status": response.status, "content_range": response.headers.get("Content-Range"),
                    "host": urlsplit(response.url).hostname}
            assert len(body) <= protocol["probe_bytes"] + 1
            path = folder / (name + ".bin")
            path.write_bytes(body)
            observed.update(bytes=len(body), prefix_sha256=hashlib.sha256(body).hexdigest(),
                file=str(path), source=url,
                exact_range=observed["status"] == 206 and len(body) == protocol["probe_bytes"]
                    and observed["content_range"] == f'bytes 0-{protocol["probe_bytes"]-1}/{artifact["size"]}')
        except Exception as error:
            observed = {"source": url, "failure": type(error).__name__ + ": " + str(error), "exact_range": False}
        observed["seconds_including_connection"] = time.perf_counter() - start
        return name, observed
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = dict(pool.map(probe, urls.items()))
    result = {"scope": protocol["scope"], "artifact_sha256_in_both_official_indexes": expected,
        "artifact_bytes": artifact["size"], "probes": results,
        "model_constructions": 0, "GPU_allocations": 0, "original_transfers_stopped": False,
        "full_wheel_verified": False}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
