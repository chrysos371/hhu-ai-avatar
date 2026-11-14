"""Reuse unchanged C49 software evidence, bind new C50 registered inputs."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
BASE = Path(__file__).resolve().parents[1]
PRIOR = BASE.parent/'cycle-49/审计'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def snapshot():
    binding = json.loads((PRIOR/'工作目录/002-当前软件与浏览器/minimal-history-v1-python-final-binding.json').read_text())
    source = binding['source_git_sha256']
    assert len(source) == 489
    assert all(digest(ROOT/name) == sha for name,sha in source.items()), 'software changed: new appropriate regression required'
    for name in ('natural-history-cases.json','natural-history-protocol.json','model-registry.json'):
        path = ROOT/'evals/interaction/cycle-50'/name
        source[str(path.relative_to(ROOT))] = digest(path)
    assert len(source) == 492
    return dict(sorted(source.items()))
