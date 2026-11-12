"""C38 candidate-only source admission and migrated native runtime identity."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[5]
BASE = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / 'evals/interaction/cycle-38/typed-capability-gate-protocol.json'
REGISTRY = ROOT / 'evals/interaction/cycle-38/model-registry.json'
REFERENCE = ROOT / 'docs/进展报告/2026-11-12-项目数据集中迁移/迁后原生运行库身份.json'
WORK = BASE / '审计/工作目录/003-原生开发配对'
RUNTIME = WORK / 'native-runtime.json'
ADMISSION = BASE / '审计/工作目录/002-工程全量/native-admission.json'
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'src'))
from avatar.paths import environment_python
from probe_structured_provider import environment


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


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
    names = set(subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode().strip('\0').split('\0'))
    names = {n for n in names if n.startswith(('src/', 'scripts/', 'tests/', 'evals/interaction/cycle-38/'))
             or (n.startswith(str((BASE / '审计').relative_to(ROOT)) + '/') and n.endswith('.py'))}
    names.update(m['metadata'] for m in read(REGISTRY)['models'])
    names.update((str(REFERENCE.relative_to(ROOT)), str(RUNTIME.relative_to(ROOT)), str(ADMISSION.relative_to(ROOT))))
    return names


def verify_source(path, expected, model='qwen3-4b-q4_k_m'):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('C38 execution descriptor bytes changed')
    frozen = json.loads(raw)
    protocol = read(PROTOCOL)
    cases = protocol['development_cases']
    if (frozen.get('candidate') != 'lab_typed_capability_gate_v1'
            or frozen.get('scope') != 'isolated_typed_capability_paired_development'
            or frozen.get('execution_authorized') is not True or frozen.get('allowed_partition') != 'development'
            or frozen.get('protected_execution_authorized') is not False or frozen.get('provider_backend') != 'cuda'
            or frozen.get('models') != ['qwen3-4b-q4_k_m'] or model != 'qwen3-4b-q4_k_m'
            or frozen.get('protocol') != str(PROTOCOL.relative_to(ROOT))
            or frozen.get('models_registry') != str(REGISTRY.relative_to(ROOT))
            or frozen.get('registry_sha256') != digest(REGISTRY)
            or protocol['models_registry_sha256'] != digest(REGISTRY)
            or frozen.get('case_ids') != [c['id'] for c in cases]
            or frozen.get('turn_count_per_arm') != sum(len(c['turns']) for c in cases)
            or frozen.get('repetitions') != protocol['sampling']['repetitions']):
        raise ValueError('C38 candidate/partition execution contract differs')
    admission = read(ADMISSION)
    if admission.get('verified') is not True or admission.get('new_native_calls') != 0:
        raise ValueError('C38 controlled admission missing')
    hashes = frozen.get('sha256')
    if not isinstance(hashes, dict) or not required_inputs() <= hashes.keys():
        raise ValueError('C38 frozen inputs incomplete')
    for name, sha in hashes.items():
        if (not isinstance(name, str) or Path(name).is_absolute()
                or not (ROOT / name).resolve().is_relative_to(ROOT) or digest(ROOT / name) != sha):
            raise ValueError('C38 execution source changed: ' + str(name))
    archive = subprocess.check_output(['git', 'archive', '--format=tar', frozen['source_ref'], '--', *sorted(hashes)], cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        historical = {m.name: hashlib.sha256(stream.extractfile(m).read()).hexdigest() for m in stream if m.isfile()}
    if historical != hashes:
        raise ValueError('C38 historical Git source differs')
    return frozen
