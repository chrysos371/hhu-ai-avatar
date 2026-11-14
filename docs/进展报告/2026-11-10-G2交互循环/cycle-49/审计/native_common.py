"""C49 source/runtime identity and retired, model-specific native admission."""
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
PROTOCOL = ROOT/'evals/interaction/cycle-49/minimal-history-trial-protocol.json'
CASES = ROOT/'evals/interaction/cycle-49/minimal-history-cases.json'
REGISTRY = ROOT/'evals/interaction/cycle-49/model-registry.json'
REFERENCE = ROOT/'docs/进展报告/2026-11-12-项目数据集中迁移/迁后原生运行库身份.json'
RUNTIME = WORK/'native-runtime.json'
WEIGHTS = WORK/'weight-identities.json'
sys.path[:0] = [str(ROOT/'scripts'),str(ROOT/'src')]
from avatar.paths import environment_python
from probe_structured_provider import environment
from run_regression import snapshot


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


def protocol_check():
    protocol = read(PROTOCOL); material = read(CASES); cases = material['cases']
    if type(protocol.get('version')) is not int or protocol['version'] != 1:
        raise ValueError('C49 requires registered version1')
    if type(material.get('registration_version')) is not int or material['registration_version'] != 1:
        raise ValueError('C49 material version differs')
    if protocol['cases_sha256'] != digest(CASES) or protocol['model_registry_sha256'] != digest(REGISTRY):
        raise ValueError('C49 registered input identity changed')
    for field in ('protected_partition_authorized','default_model_change_authorized','production_candidate_activation_authorized'):
        if protocol.get(field) is not False:
            raise ValueError('C49 is isolated diagnostic development only')
    if (len(cases) != 18 or len({c['id'] for c in cases}) != 18
            or any(type(c.get('repeat_query_after_actor')) is not bool for c in cases)
            or sum(c['repeat_query_after_actor'] for c in cases) != 6
            or protocol['arms'] != ['production_snapshot','C48_typed_control','minimal_observation']
            or protocol['primary_candidate'] != 'minimal_observation'):
        raise ValueError('C49 exact cases, requery or arms differ')
    from avatar.brain.reminder_queries import parse_query
    if any(parse_query(c['followup_text']) is not None for c in cases):
        raise ValueError('C49 followup must reach ordinary SDK model path')
    for field,value in {'repetitions':3,'cases_per_repetition':18,'arms':3,
            'trials_per_model':162,'query_turns_per_model':216,'ordinary_turns_per_model':162,
            'actual_SDK_turns_per_model':378,'native_calls_per_trial':2,'warmups_per_model':2,
            'max_native_calls_per_model':326,'models':2,'max_total_native_calls':652,
            'SQL_dumps_per_model':378,'extra_model_retries':0}.items():
        if type(protocol['sampling'].get(field)) is not int or protocol['sampling'][field] != value:
            raise ValueError('C49 sampling contract differs')
    if protocol['sampling']['whole_experiment_wallclock_cutoff'] is not None:
        raise ValueError('C49 no whole-stage wallclock cutoff')
    return protocol


def required_inputs(model_id):
    selected = set(snapshot())
    selected.update(str(p.relative_to(ROOT)) for p in (BASE/'审计').glob('*.py'))
    for folder in ('001-材料与来源调查','002-当前软件与浏览器','003-受控实模管线'):
        selected.update(str(p.relative_to(ROOT)) for p in (BASE/'审计/工作目录'/folder).rglob('*') if p.is_file())
    selected.update(str(p.relative_to(ROOT)) for p in (RUNTIME,WEIGHTS,WORK/'admission.json',WORK/'sse-controlled-v1.json',REFERENCE))
    selected.update(str(p.relative_to(ROOT)) for p in (WORK/'negative-cli-inputs').rglob('*') if p.is_file())
    for short in ('4b','14b'):
        selected.update(str((WORK/(short+suffix)).relative_to(ROOT)) for suffix in
            ('-embedded-chat-template.jinja','-template-metadata.json'))
    selected.add('docs/进展报告/2026-11-10-G2交互循环/cycle-48/审计/证据清单.json')
    if model_id == 'qwen3-14b-q4_k_m':
        folder = BASE/'实验/4b-development-v1'
        if not (WORK/'4b-retirement-verification.json').is_file():
            raise ValueError('C49 4B must finish, verify and retire before14B freeze')
        selected.update(str(p.relative_to(ROOT)) for p in folder.rglob('*') if p.is_file())
        selected.update(str((WORK/n).relative_to(ROOT)) for n in ('4b-freeze-v1.json','4b-freeze-v1-retirement.json',
            '4b-verification.json','4b-retirement-verification.json'))
    return sorted(selected)


def verify_freeze(path,expected,model_id,output_tag):
    path = Path(path).resolve()
    short = {'qwen3-4b-q4_k_m':'4b','qwen3-14b-q4_k_m':'14b'}.get(model_id)
    if short is None or path.parent != WORK.resolve() or path.name != short+'-freeze-v1.json':
        raise ValueError('C49 model-specific descriptor required')
    if type(expected) is not str or re.fullmatch(r'[0-9a-f]{64}',expected) is None or digest(path) != expected:
        raise ValueError('C49 descriptor SHA differs')
    if path.with_name(path.stem+'-retirement.json').exists():
        raise ValueError('C49 descriptor retired; do not repeat native inference')
    frozen = read(path); protocol_check()
    if (frozen.get('model_id') != model_id or frozen.get('output_tag') != output_tag
            or type(frozen.get('registration_version')) is not int or frozen['registration_version'] != 1
            or frozen.get('partition') != 'development' or frozen.get('protected_authorized') is not False
            or type(frozen.get('repetitions')) is not int or frozen['repetitions'] != 3
            or type(frozen.get('max_native_calls')) is not int or frozen['max_native_calls'] != 326):
        raise ValueError('C49 model partition sampling or output authorization differs')
    if frozen['protocol_sha256'] != digest(PROTOCOL) or frozen['registry_sha256'] != digest(REGISTRY):
        raise ValueError('C49 protocol or registry changed')
    if frozen['runtime_sha256'] != digest(RUNTIME) or frozen['weights_sha256'] != digest(WEIGHTS):
        raise ValueError('C49 native identity receipt changed')
    names = required_inputs(model_id); hashes = frozen['sha256']
    if set(names) != set(hashes) or any(digest(ROOT/n) != sha for n,sha in hashes.items()):
        raise ValueError('C49 current frozen input bytes changed')
    if historical(frozen['source_ref'],hashes) != hashes:
        raise ValueError('C49 Git source differs from frozen bytes')
    if capture_runtime() != read(RUNTIME):
        raise ValueError('C49 installed native runtime changed')
    if not read(WORK/'admission.json')['admitted']:
        raise ValueError('C49 pre-native admission incomplete')
    return frozen


def collect_sdk_stream(client,*,model,messages,max_tokens):
    events,parts = [],[]
    with client.chat.completions.create(model=model,messages=messages,temperature=0,max_tokens=max_tokens,stream=True) as stream:
        for chunk in stream:
            events.append(chunk.model_dump())
            if chunk.choices and chunk.choices[0].delta.content: parts.append(chunk.choices[0].delta.content)
    return ''.join(parts),events


