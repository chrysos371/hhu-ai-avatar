"""C43 source/admission boundaries for isolated shared-proposal native reads."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT=Path(__file__).resolve().parents[5]
BASE=Path(__file__).resolve().parents[1]
WORK=BASE/'审计/工作目录/004-原生政策依据实验'
REFERENCE=ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/迁后原生运行库身份.json'
PROTOCOL=ROOT/'evals/interaction/cycle-43/policy-question-trial-protocol.json'
REGISTRY=ROOT/'evals/interaction/cycle-43/model-registry.json'
CONTRACT=ROOT/'evals/interaction/cycle-43/policy-question-evidence-contract.json'
RUNTIME=WORK/'native-runtime.json'
REGRESS=BASE/'审计/工作目录/002-当前软件与浏览器'
CONTROLS=BASE/'审计/工作目录/003-受控政策依据'
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
    selected={n for n in names if n.startswith(('src/','scripts/','tests/','frontend/','evals/interaction/cycle-43/'))
        or n.startswith(str((BASE/'审计').relative_to(ROOT))+'/') and n.endswith('.py')}
    selected.update(read(REGRESS/'policy-evidence-python-final-binding.json')['source_git_sha256'])
    selected.update((str(REFERENCE.relative_to(ROOT)),str(RUNTIME.relative_to(ROOT))))
    selected.add('docs/进展报告/2026-11-10-G2交互循环/cycle-40/审计/工作目录/001-工具调用调查/embedded-chat-template.jinja')
    selected.update(m['metadata'] for m in read(REGISTRY)['models'])
    selected.update(str(p.relative_to(ROOT)) for directory in (CONTROLS,REGRESS) for p in directory.rglob('*') if p.is_file())
    selected.update(str((WORK/name).relative_to(ROOT)) for name in ('native-admission.json','sse-controlled-current.json'))
    if partition=='protected':
        dev=read(WORK/'development-verification.json')
        directory=(ROOT/dev['output_relative']).resolve()
        if directory.parent!=BASE/'实验':raise ValueError('invalid development archive')
        selected.update(str(p.relative_to(ROOT)) for p in directory.rglob('*') if p.is_file())
        selected.add(str((WORK/'development-verification.json').relative_to(ROOT)))
    return selected


def verify_freeze(path,expected,partition):
    path=Path(path)
    if digest(path)!=expected:raise ValueError('C43 descriptor changed')
    if path.with_name(path.stem+'-retirement.json').exists():raise ValueError('C43 descriptor retired')
    frozen=read(path);protocol=read(PROTOCOL)
    if (partition not in ('development','protected') or frozen.get('allowed_partition')!=partition
            or frozen.get('scope')!=protocol['scope'] or frozen.get('backend')!='cuda'
            or frozen.get('execution_authorized') is not True or frozen.get('model_id')!='qwen3-4b-q4_k_m'
            or frozen.get('protocol_sha256')!=digest(PROTOCOL) or frozen.get('registry_sha256')!=digest(REGISTRY)
            or protocol['source_contract_sha256']!=digest(CONTRACT)
            or protocol['model_registry_sha256']!=digest(REGISTRY)
            or frozen.get('case_ids')!=[c['id'] for c in protocol[partition+'_cases']]
            or frozen.get('repetitions')!=protocol['sampling'][partition+'_repetitions']
            or frozen.get('max_native_calls')!=protocol['sampling'][partition+'_max_native_calls']):
        raise ValueError('C43 execution contract changed')
    admission=read(WORK/'native-admission.json')
    if not admission.get('verified') or admission.get('protected_authorized') is not False:
        raise ValueError('C43 development admission missing')
    if partition=='protected' and not read(WORK/'development-verification.json').get('primary_gate_passed'):
        raise ValueError('C43 primary development gate not met')
    hashes=frozen['sha256']
    if not required_inputs(partition)<=hashes.keys():raise ValueError('C43 frozen inputs incomplete')
    for name,sha in hashes.items():
        p=ROOT/name
        if Path(name).is_absolute() or not p.resolve().is_relative_to(ROOT) or digest(p)!=sha:
            raise ValueError('C43 source changed: '+name)
    if historical(frozen['source_ref'],hashes)!=hashes:raise ValueError('C43 Git source differs')
    if capture_runtime()!=read(RUNTIME):raise ValueError('C43 native runtime identity changed')
    return frozen


if __name__=='__main__':
    WORK.mkdir(parents=True,exist_ok=True)
    assert not RUNTIME.exists()
    RUNTIME.write_text(json.dumps(capture_runtime(),ensure_ascii=False,indent=2)+'\n')
    print('C43 native import/54 library identities matched;0 model construction')
