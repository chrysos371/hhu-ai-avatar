"""C50 source/runtime identity and retired, model-specific native admission."""
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[5]
BASE = Path(__file__).resolve().parents[1]
WORK = BASE/'审计/工作目录/004-原生准入'
REGRESS = BASE/'审计/工作目录/002-当前软件与浏览器'
CONTROLS = BASE/'审计/工作目录/003-受控实模管线'
PROTOCOL = ROOT/'evals/interaction/cycle-50/natural-history-protocol.json'
CASES = ROOT/'evals/interaction/cycle-50/natural-history-cases.json'
REGISTRY = ROOT/'evals/interaction/cycle-50/model-registry.json'
REFERENCE = ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/迁后原生运行库身份.json'
RUNTIME = WORK/'native-runtime.json'
WEIGHTS = WORK/'weight-identities.json'
sys.path[:0] = [str(ROOT/'scripts'),str(ROOT/'src')]
from avatar.paths import environment_python
from probe_structured_provider import environment
from source_identity import snapshot


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''): h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def historical(ref,names):
    raw = subprocess.check_output(['git','archive','--format=tar',ref,'--',*sorted(names)],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        return {m.name:hashlib.sha256(archive.extractfile(m).read()).hexdigest() for m in archive if m.isfile()}


def capture_runtime():
    reference = read(REFERENCE); python = environment_python(native=True)
    code = ('import sys,json,importlib.metadata as m,llama_cpp; print(json.dumps({"executable":sys.executable,'
        '"prefix":sys.prefix,"package_root":str(__import__("pathlib").Path(llama_cpp.__file__).parent),'
        '"package_versions":{k:m.version(k) for k in '+repr(list(reference['package_versions']))+'}}))')
    actual = json.loads(subprocess.check_output([str(python),'-c',code],cwd=ROOT,env=environment(python),text=True))
    assert actual['prefix'] == reference['python_prefix'] and actual['package_root'] == reference['package_root']
    assert actual['package_versions'] == reference['package_versions']
    actual['files_sha256'],cache = {},{}
    for name,sha in reference['files_sha256'].items():
        path = Path(name)
        if path.resolve() not in cache: cache[path.resolve()] = digest(path)
        actual['files_sha256'][name] = cache[path.resolve()]
        assert cache[path.resolve()] == sha,name
    assert len(actual['files_sha256']) == 54
    actual.update(reference_sha256=digest(REFERENCE),model_inference_calls=0,
        scope='installed native library import identity only; no model construction')
    return actual


