"""Preregistered native restart/use source contract; no production activation."""
from hashlib import sha256
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5]
BASE=Path(__file__).resolve().parents[1]
OLD=BASE.parent/'cycle-29/审计'
PROTOCOL='evals/interaction/cycle-30/native-context-use-protocol.json'
REGISTRY='evals/interaction/cycle-26/model-scale-registry.json'
MODELS=('qwen3-4b-q4_k_m','qwen3-32b-q4_k_m')
ARMS=('optout_restart','recovered_restart')


def digest(path):return sha256(path.read_bytes()).hexdigest()


def source_paths():
    paths={PROTOCOL,REGISTRY}
    paths.update(str(p.relative_to(ROOT)) for g in ('src','tests','scripts') for p in (ROOT/g).rglob('*.py'))
    paths.update('evals/interaction/cycle-26/model-metadata-'+label+'.json' for label in ('4b','14b','32b'))
    paths.update(str((OLD/n).relative_to(ROOT)) for n in ('context_baseline_common.py','context_fault_common.py','run_context_baseline.py','run_context_fault_controls.py'))
    paths.update(str((BASE/'审计'/n).relative_to(ROOT)) for n in ('context_native_common.py','context_native_worker.py','context_native_relay.py','run_native_context_use.py'))
    return paths


def verify_freeze(path,expected,model=None):
    if digest(path)!=expected:raise ValueError('Native context freeze identity changed')
    value=json.loads(path.read_text());protocol=json.loads((ROOT/PROTOCOL).read_text())
    for d in (value,protocol):
        if (d.get('scope')!='actual_native_web_os_restart_context_use_development' or d.get('backend')!='cuda'
                or d.get('models')!=list(MODELS) or d.get('arms')!=list(ARMS) or d.get('app_turns_per_model')!=36
                or d.get('expected_app_processes_per_model')!=24 or d.get('expected_model_http_calls_per_model')!=74
                or d.get('production_activation_authorized') is not False or d.get('prospective_execution_authorized') is not False):raise ValueError('Native context execution contract mismatch')
    if model is not None and model not in MODELS:raise ValueError('Unexpected native context model')
    cases=protocol['cases'];assert len(cases)==6 and len({c['id'] for c in cases})==6
    assert len(protocol['case_arm_orders'])==6 and all(sorted(order)==sorted(ARMS) for order in protocol['case_arm_orders'])
    assert all(len(c['turns'])==3 and all(isinstance(t,str) and 0<len(t)<=4000 for t in c['turns']) for c in cases)
    if not source_paths()<=value.get('sha256',{}).keys():raise ValueError('Native context source inputs missing')
    for name,identity in value['sha256'].items():
        p=ROOT/name
        if not p.resolve().is_relative_to(ROOT) or digest(p)!=identity:raise ValueError('Native context input changed: '+name)
    return value


def require_loopback(url):
    from urllib.parse import urlsplit
    u=urlsplit(url)
    if u.scheme!='http' or u.hostname!='127.0.0.1' or not u.port or u.path!='/v1' or u.username or u.password or u.query or u.fragment:raise ValueError('Owned loopback provider required')


def runtime_modules():
    import sys
    result={}
    for name,module in list(sys.modules.items()):
        if (name=='avatar' or name.startswith('avatar.')) and getattr(module,'__file__',None):
            path=Path(module.__file__).resolve()
            if not path.is_relative_to(ROOT/'src'):raise ValueError('Foreign Avatar runtime')
            result[name]={'path':str(path),'sha256':digest(path)}
    return result
