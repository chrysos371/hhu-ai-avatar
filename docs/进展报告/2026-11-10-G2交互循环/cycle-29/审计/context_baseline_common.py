"""Source-bound controlled-HTTP context audit; no real model/production release."""
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[5]
BASE=Path(__file__).resolve().parents[1]
PROTOCOL='evals/interaction/cycle-29/context-continuity-baseline-protocol.json'


def digest(path):return sha256(path.read_bytes()).hexdigest()


def source_paths():
    names={PROTOCOL}
    names.update(str(path.relative_to(ROOT)) for group in ('src','scripts') for path in (ROOT/group).rglob('*.py'))
    names.update(str((BASE/'审计'/name).relative_to(ROOT)) for name in ('context_baseline_common.py','context_baseline_worker.py','run_context_baseline.py'))
    return names


def verify_freeze(path,expected):
    if digest(path)!=expected:raise ValueError('Baseline freeze identity changed')
    value=json.loads(path.read_text())
    if (value.get('scope')!='actual_http_os_restart_llm_context_baseline'
            or value.get('provider_kind')!='controlled_loopback_fixture' or value.get('actual_llm_or_gpu') is not False
            or value.get('case_ids')!=['same_instance','new_os_instance'] or value.get('app_turns')!=6):raise ValueError('Baseline execution contract mismatch')
    if not source_paths()<=value.get('sha256',{}).keys():raise ValueError('Baseline source inputs missing')
    for name,identity in value['sha256'].items():
        target=ROOT/name
        if not target.resolve().is_relative_to(ROOT) or digest(target)!=identity:raise ValueError('Baseline input changed: '+name)
    return value


def require_loopback(url):
    address=urlsplit(url)
    if (address.scheme!='http' or address.hostname!='127.0.0.1' or not address.port
            or address.path!='/v1' or address.username or address.password or address.query or address.fragment):raise ValueError('Controlled loopback fixture URL required')


def runtime_modules():
    import sys
    result={}
    for name,module in list(sys.modules.items()):
        if (name=='avatar' or name.startswith('avatar.')) and getattr(module,'__file__',None):
            path=Path(module.__file__).resolve()
            if not path.is_relative_to(ROOT/'src'):raise ValueError('Foreign Avatar runtime module: '+name)
            result[name]={'path':str(path),'sha256':digest(path)}
    return result
