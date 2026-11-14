"""Register exact official Torch/CUDA wheel identities; no installation or full download."""
from concurrent.futures import ThreadPoolExecutor
from email.parser import BytesParser
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import urllib.request
from urllib.parse import unquote, urlsplit, urldefrag, urljoin

from packaging.requirements import Requirement
from packaging.tags import sys_tags
from packaging.utils import parse_wheel_filename

WORK = Path(__file__).parent / "工作目录/008-CUDA完整依赖缓存"


class Links(HTMLParser):
    def __init__(self, data):
        super().__init__()
        self.links = []
        self.feed(data.decode())

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "a" and values.get("href"):
            self.links.append(values)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    protocol = json.loads((WORK / "registry-protocol-v1.json").read_text())
    output = WORK / "wheel-registry-v2.json"
    raw_folder = WORK / "metadata-v2"
    raw_folder.mkdir(exist_ok=False)
    assert not output.exists()
    ranks = {tag: n for n, tag in enumerate(sys_tags())}
    def fetch(url, name):
        with urllib.request.urlopen(url, timeout=60) as response:
            raw = response.read(protocol["metadata_max_bytes"] + 1)
        assert len(raw) <= protocol["metadata_max_bytes"]
        path = raw_folder / name
        assert not path.exists()
        path.write_bytes(raw)
        return raw
    def select(package, version, exact=None):
        index = f"https://download.pytorch.org/whl/cu124/{package}/"
        raw = fetch(index, package + "-index-v1.html.txt")
        matches = []
        for link in Links(raw).links:
            url, fragment = urldefrag(urljoin(index, link["href"]))
            filename = unquote(Path(urlsplit(url).path).name)
            if exact is not None and filename != exact:
                continue
            try:
                name, actual, _, tags = parse_wheel_filename(filename)
            except Exception:
                continue
            if str(actual) != version or not (set(tags) & set(ranks)):
                continue
            assert name.replace("_", "-") == package.replace("_", "-")
            assert fragment.startswith("sha256=") and len(fragment) == 71
            matches.append((min(ranks[t] for t in tags if t in ranks), filename, url, fragment[7:], link))
        assert matches, (package, version, "no compatible exact-version wheel")
        _, filename, url, digest, link = sorted(matches, key=lambda m: (m[0], m[1]))[0]
        assert url.startswith("https://")
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=60) as response:
            size = int(response.headers["Content-Length"])
        assert size > 0
        return {"package": package, "version": version, "filename": filename, "url": url,
            "sha256": digest, "bytes": size, "official_index": index,
            "index_sha256": sha(raw)}, link
    torch, link = select("torch", protocol["torch_version"], protocol["torch_filename"])
    metadata = fetch(torch["url"] + ".metadata", "torch-wheel-v1.metadata.txt")
    metadata_digest = link.get("data-core-metadata", link.get("data-dist-info-metadata"))
    assert metadata_digest and metadata_digest == "sha256=" + sha(metadata)
    parsed = BytesParser().parsebytes(metadata)
    assert parsed["Version"] == protocol["torch_version"]
    needed = []
    for value in parsed.get_all("Requires-Dist"):
        requirement = Requirement(value)
        if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
            continue
        if requirement.name.startswith("nvidia-") or requirement.name == "triton":
            specs = list(requirement.specifier)
            assert len(specs) == 1 and specs[0].operator == "=="
            needed.append((requirement.name, specs[0].version))
    assert len(needed) >= 10
    artifacts = [torch]
    def dependency(item):
        result, _ = select(*item)
        print("registered", result["package"], result["version"], result["bytes"], flush=True)
        return result
    with ThreadPoolExecutor(max_workers=protocol["metadata_workers"]) as pool:
        artifacts.extend(pool.map(dependency, needed))
    result = {"scope": protocol["scope"], "artifacts": artifacts,
        "official_torch_metadata_sha256": sha(metadata), "source_sha256": sha(Path(__file__).read_bytes()),
        "protocol_sha256": sha((WORK / "registry-protocol-v1.json").read_bytes()),
        "total_bytes": sum(f["bytes"] for f in artifacts), "full_wheels_verified": False,
        "original_transfers_continue": True, "environment_mutated": False,
        "model_constructions": 0, "GPU_allocations": 0, "training_steps": 0}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print("C51 registered exact Torch/CUDA wheels", len(artifacts), "bytes", result["total_bytes"], ";no install/full download", flush=True)


if __name__ == "__main__":
    main()
