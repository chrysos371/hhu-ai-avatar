"""Source/runtime identity and contract for known-wire native state isolation."""
from hashlib import sha256
import importlib.metadata
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
ROOT=Path(__file__).resolve().parents[5];BASE=Path(__file__).resolve().parents[1]
PROTOCOL='evals/interaction/cycle-32/state-isolation-protocol.json'
FIXTURES='evals/interaction/cycle-32/retained-material-wire-fixtures.json'
RUNTIME='evals/interaction/cycle-32/backend-runtime-identity.json'
REGISTRY='evals/interaction/cycle-26/model-scale-registry.json'
MODELS=('qwen3-4b-q4_k_m','qwen3-32b-q4_k_m');POLICIES=('reuse','logical_reset','memory_clear_reset')


def digest(path):
    h=sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()


def source_paths():
    paths={PROTOCOL,FIXTURES,RUNTIME,REGISTRY}
    paths.update(str(p.relative_to(ROOT)) for g in ('src','tests','scripts') for p in (ROOT/g).rglob('*.py'))
    paths.update('evals/interaction/cycle-26/model-metadata-'+m+'.json' for m in ('4b','14b','32b'))
    paths.add(str((BASE.parent/'cycle-31/审计/证据清单.json').relative_to(ROOT)))
    paths.update(str((BASE/'审计'/n).relative_to(ROOT)) for n in ('state_common.py','state_policy.py','serve_state_eval.py','run_state_replay.py','probe_policy_cpu.py'))
    paths.update(str((BASE/'审计/工作目录/001-原生状态隔离'/n).relative_to(ROOT)) for n in ('实现参考与版本绑定.json','policy-cpu-controls.json','policy-cpu-controls.log','cpu-control-version.json'))
    return paths


def verify_freeze(path,expected,model=None):
    if digest(path)!=expected:raise ValueError('State replay freeze identity changed')
    frozen=json.loads(Path(path).read_text());protocol=json.loads((ROOT/PROTOCOL).read_text())
    for data in (frozen,protocol):
        if (data.get('scope')!='native_retained_wire_state_isolation_regression_replay' or data.get('backend')!='cuda'
                or data.get('models')!=list(MODELS) or data.get('state_policies')!=list(POLICIES) or data.get('repetitions')!=3
                or data.get('model_http_calls_per_model')!=105 or data.get('model_http_calls_per_policy')!=35
                or data.get('production_activation_authorized') is not False or data.get('prospective_execution_authorized') is not False):raise ValueError('State replay execution contract mismatch')
    if model is not None and model not in MODELS:raise ValueError('Unexpected state replay model')
    if any(sorted(protocol['policy_orders'].get(m,[]))!=sorted(POLICIES) for m in MODELS) or len(protocol['chain_orders'])!=3 or any(sorted(order)!=['with_extra_cognitive','without_extra_cognitive'] for order in protocol['chain_orders']):raise ValueError('State replay policy/chain schedule changed')
    if protocol['warmups']!=[False,True] or protocol['diagnostic_calls_per_policy']!=33:raise ValueError('State replay warmup/count contract changed')
    if not source_paths()<=frozen.get('sha256',{}).keys():raise ValueError('State replay source inputs missing')
    for name,value in frozen['sha256'].items():
        path=ROOT/name
        if not path.resolve().is_relative_to(ROOT) or digest(path)!=value:raise ValueError('State replay source changed: '+name)
    if protocol['fixtures_sha256']!=digest(ROOT/FIXTURES) or protocol['backend_runtime_identity_sha256']!=digest(ROOT/RUNTIME):raise ValueError('State replay fixtures/runtime identity changed')
    return frozen


def verify_historical_binding(frozen):
    raw=subprocess.check_output(['git','archive','--format=tar',frozen['source_ref'],'--',*sorted(frozen['sha256'])],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as archive:
        actual={m.name:sha256(archive.extractfile(m).read()).hexdigest() for m in archive.getmembers() if m.isfile()}
    if actual!=frozen['sha256']:raise ValueError('State replay historical source bytes differ')


def verify_backend(path,expected,*,require_native_process=False):
    path=Path(path)
    if path.resolve()!= (ROOT/RUNTIME).resolve() or digest(path)!=expected:raise ValueError('Backend runtime manifest identity differs')
    data=json.loads(path.read_text());native=(ROOT.parent/'envs/hhu-ai-avatar-llm').resolve();gpu=(ROOT.parent/'runtime/gpu-libs').resolve()
    if data['package_versions']['llama-cpp-python']!='0.3.19' or Path(data['python_prefix']).resolve()!=native:raise ValueError('Unexpected native package contract')
    if require_native_process and (Path(sys.prefix).resolve()!=native or importlib.metadata.version('llama-cpp-python')!='0.3.19'):raise ValueError('Provider did not use registered native environment')
    for name,value in data['files_sha256'].items():
        target=Path(name).resolve()
        if not any(target.is_relative_to(root) for root in (native,gpu)) or digest(target)!=value:raise ValueError('Native package/runtime library changed: '+name)
    return data


def validate_fixture_provenance(model):
    fixture=json.loads((ROOT/FIXTURES).read_text());entry=next(m for m in fixture['models'] if m['model_id']==model)
    seal=BASE.parent/'cycle-31/审计/证据清单.json'
    if digest(seal)!=fixture['source_cycle31_manifest_sha256']:raise ValueError('Historical C31 seal differs')
    original=ROOT/entry['source_evaluation'];relative=str(original.relative_to(BASE.parent/'cycle-31'))
    if digest(original)!=entry['source_evaluation_sha256'] or json.loads(seal.read_text())[relative]!=entry['source_evaluation_sha256']:raise ValueError('Historical SDK source evidence changed')
    data=json.loads(original.read_text());group=next(c for c in data['cases'] if c['id']==entry['source_group']);actual=group['model_requests']
    if data['model_id']!=model or data['provider_ready']['chosen_gpu']!=entry['source_gpu']:raise ValueError('Historical model/GPU fixture metadata mismatch')
    if len(actual)!=6:raise ValueError('Historical source chain changed')
    for row,source in zip(entry['requests'],actual,strict=True):
        if row['raw_request_json']!=source['raw_request_json'] or sha256(row['raw_request_json'].encode()).hexdigest()!=row['request_sha256']:raise ValueError('Replay payload is not retained SDK bytes')
    if entry['chains']!={'without_extra_cognitive':[0,1,2,3,5],'with_extra_cognitive':[0,1,2,3,4,5]}:raise ValueError('Replay chain order changed')
    return entry
