"""C40 standalone tool wire admission; no production or protected authorization."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT=Path(__file__).resolve().parents[5]
BASE=Path(__file__).resolve().parents[1]
WORK=BASE/'审计/工作目录/003-原生工具wire'
REFERENCE=ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/迁后原生运行库身份.json'
PROTOCOL=ROOT/'evals/interaction/cycle-40/native-tool-wire-protocol.json'
REGISTRY=ROOT/'evals/interaction/cycle-40/model-registry.json'
RUNTIME=WORK/'native-runtime.json'
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from avatar.paths import environment_python
from probe_structured_provider import environment


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()


def read(path):return json.loads(Path(path).read_text())

def capture_runtime():
    reference = read(REFERENCE)
    python = environment_python(native=True)
    code = ('import sys,json,importlib.metadata as m,llama_cpp; print(json.dumps({"executable":sys.executable,'
        '"prefix":sys.prefix,"package_root":str(__import__("pathlib").Path(llama_cpp.__file__).parent),'
        '"package_versions":{k:m.version(k) for k in '+repr(list(reference['package_versions']))+'}}))')
    actual = json.loads(subprocess.check_output([str(python), '-c', code], cwd=ROOT, env=environment(python), text=True))
    assert actual['prefix'] == reference['python_prefix'] and actual['package_root'] == reference['package_root']
    assert actual['package_versions'] == reference['package_versions']
    actual['files_sha256'], cache = {}, {}
    for name, sha in reference['files_sha256'].items():
        path = Path(name)
        if path.resolve() not in cache:
            cache[path.resolve()] = digest(path)
        actual['files_sha256'][name] = cache[path.resolve()]
        assert cache[path.resolve()] == sha, name
    assert len(actual['files_sha256']) == 54
    actual.update(reference_sha256=digest(REFERENCE), model_inference_calls=0,
        scope='installed_library_import_identity_only_not_model_construction')
    return actual


def required_inputs():
    names=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    selected={n for n in names if n.startswith(('src/','scripts/','tests/','evals/interaction/cycle-40/'))
        or n.startswith(str((BASE/'审计').relative_to(ROOT))+'/') and n.endswith('.py')}
    selected.update((str(REFERENCE.relative_to(ROOT)),str(RUNTIME.relative_to(ROOT))))
    selected.update(str(p.relative_to(ROOT)) for p in (BASE/'审计/工作目录/001-工具调用调查').glob('*') if p.name in ('gguf-template.json','embedded-chat-template.jinja','content-fixed-controls.log'))
    selected.update(str((WORK/name).relative_to(ROOT)) for name in ('native-admission-sse-fixed.json','handoff-admission-sse-fixed.json','sse-controlled.json'))
    selected.update(m['metadata'] for m in read(REGISTRY)['models'])
    regress=BASE/'审计/工作目录/004-当前软件与浏览器'
    selected.update(str(p.relative_to(ROOT)) for p in regress.glob('wire-python-final*'))
    controlled=BASE/'审计/工作目录/002-受控HTTP交接/content-fixed'
    for label in ('default','opt-in'):
        for name in ('evaluation.json','execution-inputs.json','worker-cleanup.json','worker-exit.json','provider-trace.jsonl'):
            selected.add(str((controlled/label/name).relative_to(ROOT)))
    return selected


def historical(ref,names):
    raw=subprocess.check_output(['git','archive','--format=tar',ref,'--',*sorted(names)],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        return {m.name:hashlib.sha256(archive.extractfile(m).read()).hexdigest() for m in archive if m.isfile()}


def verify_freeze(path,expected):
    if Path(path).with_name(Path(path).stem+'-retirement.json').exists():raise ValueError('C40 descriptor retired')
    if digest(path)!=expected:raise ValueError('C40 descriptor changed')
    frozen=read(path);protocol=read(PROTOCOL)
    if (frozen.get('scope')!='standalone_native_tool_wire_diagnostic_not_Avatar_or_business_execution'
            or frozen.get('backend')!='cuda' or frozen.get('execution_authorized') is not True
            or frozen.get('protected_execution_authorized') is not False
            or frozen.get('model_id')!='qwen3-4b-q4_k_m' or frozen.get('max_native_calls')!=41
            or frozen.get('registry_sha256')!=digest(REGISTRY)
            or frozen.get('protocol_sha256')!=digest(PROTOCOL)
            or protocol['models_registry_sha256']!=digest(REGISTRY)):
        raise ValueError('C40 execution contract changed')
    admission=read(WORK/'native-admission-sse-fixed.json')
    handoff=read(WORK/'handoff-admission-sse-fixed.json')
    if not admission.get('verified') or not handoff.get('verified'):raise ValueError('C40 admission missing')
    if any(digest(ROOT/n)!=sha for n,sha in handoff['source_sha256'].items()):raise ValueError('C40 controller handoff source changed')
    hashes=frozen['sha256']
    if not required_inputs()<=hashes.keys():raise ValueError('C40 required source incomplete')
    for name,sha in hashes.items():
        p=ROOT/name
        if Path(name).is_absolute() or not p.resolve().is_relative_to(ROOT) or digest(p)!=sha:
            raise ValueError('C40 source changed: '+name)
    if historical(frozen['source_ref'],hashes)!=hashes:raise ValueError('C40 Git bytes mismatch')
    current_runtime=capture_runtime()
    if read(RUNTIME)!=current_runtime:raise ValueError('C40 native runtime identity changed')
    return frozen


if __name__=='__main__':
    WORK.mkdir(parents=True,exist_ok=True)
    assert not RUNTIME.exists()
    RUNTIME.write_text(json.dumps(capture_runtime(),ensure_ascii=False,indent=2)+'\n')
    print('C40 native runtime import/54 library identities matched;0 model construction')
