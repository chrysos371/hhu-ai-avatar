from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.request
import urllib.error

PROJECT = Path(__file__).resolve().parents[3]
WORKSPACE = PROJECT.parent


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def write_json(path, value):
    atomic_text(path, canonical(value) + "\n")


def atomic_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as f:
        temporary = Path(f.name)
        try:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    temporary.replace(path)


def new_output(path):
    path = Path(path).resolve()
    if not path.is_relative_to(WORKSPACE):
        raise ValueError("Output must stay in this workspace")
    if path.exists() and any(path.iterdir()):
        raise ValueError("Output must be new or empty")
    path.mkdir(parents=True, exist_ok=True)
    return path


def fetch(url, *, limit=32 * 1024 * 1024):
    if not url.startswith("https://"):
        raise ValueError("HTTPS source required")
    req = urllib.request.Request(url, headers={"User-Agent": "hhu-avatar-research/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                if not response.url.startswith("https://"):
                    raise ValueError("Insecure redirect")
                data = response.read(limit + 1)
            if len(data) > limit:
                raise ValueError("Source exceeds download bound")
            return data
        except urllib.error.HTTPError as exc:
            if exc.code < 500 or attempt == 2:
                raise
        except (OSError, ConnectionError) as exc:
            if attempt == 2:
                raise


def get_json(url):
    return json.loads(fetch(url))


def normalize(text):
    return re.sub(r"[^\w\u4e00-\u9fff]", "", text.casefold())


def source_state():
    paths = sorted((PROJECT / "src/avatar").rglob("*.py"))
    return {
        "files": {str(p.relative_to(PROJECT)): sha(p) for p in paths},
        "git_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True
        ).strip(),
        "dirty_diff_sha256": hashlib.sha256(
            subprocess.check_output(["git", "diff", "HEAD"], cwd=PROJECT)
        ).hexdigest(),
    }
