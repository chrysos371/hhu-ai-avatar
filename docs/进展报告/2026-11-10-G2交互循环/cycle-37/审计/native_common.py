"""C37 source and migrated installed-runtime identity; no model construction here."""
import hashlib, io, json, os
from pathlib import Path
import subprocess, sys, tarfile
ROOT=Path(__file__).resolve().parents[5]
BASE=Path(__file__).resolve().parents[1]
PROTOCOL=ROOT/'evals/interaction/cycle-37/current-default-capability-protocol.json'
REGISTRY=ROOT/'evals/interaction/cycle-37/model-registry.json'
REFERENCE=ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/迁后原生运行库身份.json'
WORK=BASE/'审计/工作目录/001-默认能力基线'
RUNTIME=WORK/'native-runtime.json'
sys.path.insert(0,str(ROOT/'scripts'));sys.path.insert(0,str(ROOT/'src'))
from avatar.paths import environment_python
from probe_structured_provider import environment
from evaluate_native_output_audit import verify_execution_freeze

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()
def read(path):return json.loads(Path(path).read_text())
def capture_runtime():
    reference=read(REFERENCE);python=environment_python(native=True)
    code='import sys,json,importlib.metadata as m,llama_cpp; print(json.dumps({"executable":sys.executable,"prefix":sys.prefix,"package_root":str(__import__("pathlib").Path(llama_cpp.__file__).parent),"package_versions":{k:m.version(k) for k in '+repr(list(reference['package_versions']))+'}}))'
    actual=json.loads(subprocess.check_output([str(python),'-c',code],cwd=ROOT,env=environment(python),text=True))
    assert actual['prefix']==reference['python_prefix'] and actual['package_root']==reference['package_root']
    assert actual['package_versions']==reference['package_versions']
    actual['files_sha256']={};cache={}
    for name,sha in reference['files_sha256'].items():
        path=Path(name);resolved=path.resolve()
        if resolved not in cache:cache[resolved]=digest(path)
        actual['files_sha256'][name]=cache[resolved]
        assert cache[resolved]==sha,name
    assert len(actual['files_sha256'])==54
    actual.update(reference_sha256=digest(REFERENCE),model_inference_calls=0,
        scope='installed_package_and_library_identity_import_only_no_model_construction')
    return actual

def verify_source(path,expected,model=None):
    frozen=verify_execution_freeze(path,expected,PROTOCOL,model_id=model)
    raw=subprocess.check_output(['git','archive','--format=tar',frozen['source_ref'],'--',*sorted(frozen['sha256'])],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        historical={m.name:hashlib.sha256(archive.extractfile(m).read()).hexdigest() for m in archive if m.isfile()}
    assert historical==frozen['sha256']
    return frozen
