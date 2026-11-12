"""C41 source/admission boundaries for isolated shared-proposal native reads."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT=Path(__file__).resolve().parents[5]
BASE=Path(__file__).resolve().parents[1]
WORK=BASE/'审计/工作目录/004-原生开发配对'
REFERENCE=ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/迁后原生运行库身份.json'
PROTOCOL=ROOT/'evals/interaction/cycle-41/source-checked-read-repair-protocol.json'
REGISTRY=ROOT/'evals/interaction/cycle-41/model-registry.json'
CONTRACT=ROOT/'evals/interaction/cycle-41/trusted-local-read-contract.json'
RUNTIME=WORK/'native-runtime.json'
REGRESS=BASE/'审计/工作目录/002-当前软件与浏览器'
CONTROLS=BASE/'审计/工作目录/003-受控读取配对'
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from avatar.paths import environment_python
from probe_structured_provider import environment


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()


def read(path):return json.loads(Path(path).read_text())


def historical(ref,names):
    raw=subprocess.check_output(['git','archive','--format=tar',ref,'--',*sorted(names)],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        return {m.name:hashlib.sha256(archive.extractfile(m).read()).hexdigest() for m in archive if m.isfile()}


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

def collect_sdk_stream(client,*,model,messages,max_tokens):
    """Use the same observed synchronous SDK client for SSE warmup only."""
    events=[];parts=[]
    with client.chat.completions.create(model=model,messages=messages,temperature=0,
            max_tokens=max_tokens,stream=True) as stream:
        for chunk in stream:
            events.append(chunk.model_dump())
            if chunk.choices and chunk.choices[0].delta.content:
                parts.append(chunk.choices[0].delta.content)
    reasons=[c['finish_reason'] for e in events for c in e['choices'] if c['finish_reason'] is not None]
    if reasons!=['stop']:raise ValueError('SDK SSE warmup did not stop completely')
    return {'role':'assistant','content':''.join(parts)},events


def required_inputs(partition):
    names=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    selected={n for n in names if n.startswith(('src/','scripts/','tests/','frontend/','evals/interaction/cycle-41/'))
        or n.startswith(str((BASE/'审计').relative_to(ROOT))+'/') and n.endswith('.py')}
    selected.update(read(REGRESS/'source-read-python-final-binding.json')['source_git_sha256'])
    selected.update((str(REFERENCE.relative_to(ROOT)),str(RUNTIME.relative_to(ROOT))))
    selected.add('docs/进展报告/2026-11-10-G2交互循环/cycle-40/审计/工作目录/001-工具调用调查/embedded-chat-template.jinja')
    selected.update(m['metadata'] for m in read(REGISTRY)['models'])
    selected.update(str(p.relative_to(ROOT)) for directory in (CONTROLS,REGRESS) for p in directory.rglob('*') if p.is_file())
    selected.update(str((WORK/name).relative_to(ROOT)) for name in ('native-admission.json','handoff-admission.json','sse-controlled.json'))
    if partition=='protected':
        dev_directory=ROOT/read(WORK/'development-verification.json')['output_relative']
        if not dev_directory.resolve().is_relative_to((BASE/'实验').resolve()):raise ValueError('C41 invalid development archive')
        selected.update(str(p.relative_to(ROOT)) for p in dev_directory.rglob('*') if p.is_file())
        selected.update(str((WORK/name).relative_to(ROOT)) for name in ('development-verification.json','protected-admission.json'))
    return selected


def verify_freeze(path,expected,partition):
    path=Path(path)
    if path.with_name(path.stem+'-retirement.json').exists():raise ValueError('C41 descriptor retired')
    if digest(path)!=expected:raise ValueError('C41 descriptor changed')
    frozen=read(path);protocol=read(PROTOCOL);admission=read(WORK/'native-admission.json')
    if (partition not in ('development','protected') or frozen.get('allowed_partition')!=partition
            or frozen.get('scope')!=protocol['scope'] or frozen.get('backend')!='cuda'
            or frozen.get('execution_authorized') is not True
            or frozen.get('model_id')!='qwen3-4b-q4_k_m'
            or frozen.get('protocol_sha256')!=digest(PROTOCOL)
            or frozen.get('registry_sha256')!=digest(REGISTRY)
            or protocol['source_contract_sha256']!=digest(CONTRACT)
            or protocol['model_registry_sha256']!=digest(REGISTRY)
            or frozen.get('case_ids')!=[c['id'] for c in protocol[partition+'_cases']]
            or frozen.get('repetitions')!=(3 if partition=='development' else 1)
            or frozen.get('max_native_calls')!=(50 if partition=='development' else 16)):
        raise ValueError('C41 execution contract changed')
    # The original read-contract CPU registration is retained unchanged. This
    # later, explicitly scoped admission advances only frozen development.
    if (not admission.get('verified') or admission.get('new_native_calls')!=0
            or admission.get('development_stage_authorized_after_source_freeze') is not True
            or admission.get('supersedes_CPU_registration_only_for_frozen_development') is not True
            or admission.get('protected_stage_authorized') is not False
            or read(CONTRACT)['native_execution_authorized'] is not False):
        raise ValueError('C41 staged development authorization missing')
    if partition=='protected':
        protected=read(WORK/'protected-admission.json')
        dev=read(WORK/'development-verification.json')
        if (not dev.get('verified') or not dev.get('selection_and_source_gate_passed')
                or protected.get('development_evidence_sha256')!=digest(WORK/'development-verification.json')
                or protected.get('authorizes_protected_descriptor_only') is not True
                or frozen.get('protected_execution_authorized') is not True):
            raise ValueError('C41 protected gate not met')
    elif frozen.get('protected_execution_authorized') is not False:
        raise ValueError('C41 development cannot authorize protected')
    handoff=read(WORK/'handoff-admission.json')
    if not handoff.get('verified') or any(digest(ROOT/n)!=sha for n,sha in handoff['source_sha256'].items()):
        raise ValueError('C41 current controller handoff differs')
    hashes=frozen['sha256']
    if not required_inputs(partition)<=hashes.keys():raise ValueError('C41 frozen inputs incomplete')
    for name,sha in hashes.items():
        p=ROOT/name
        if Path(name).is_absolute() or not p.resolve().is_relative_to(ROOT) or digest(p)!=sha:
            raise ValueError('C41 source changed: '+name)
    if historical(frozen['source_ref'],hashes)!=hashes:raise ValueError('C41 Git source differs')
    if capture_runtime()!=read(RUNTIME):raise ValueError('C41 native runtime identity changed')
    return frozen


if __name__=='__main__':
    WORK.mkdir(parents=True,exist_ok=True)
    assert not RUNTIME.exists()
    RUNTIME.write_text(json.dumps(capture_runtime(),ensure_ascii=False,indent=2)+'\n')
    print('C41 native import/54 library identities matched;0 model construction')
