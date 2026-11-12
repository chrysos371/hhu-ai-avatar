"""Explicit delegated timing contract, distinct from uninstrumented fault runs."""
import json
from context_fault_common import source_paths as fault_paths
from context_baseline_common import ROOT,BASE,digest,require_loopback,runtime_modules
PROTOCOL='evals/interaction/cycle-29/context-transaction-interleaving-protocol.json'


def source_paths():
    return fault_paths()|{PROTOCOL}|{str((BASE/'审计'/n).relative_to(ROOT)) for n in ('context_race_common.py','context_race_worker.py','run_context_transaction_race.py')}


def verify_freeze(path,expected):
    if digest(path)!=expected:raise ValueError('Race freeze identity changed')
    data=json.loads(path.read_text());protocol=json.loads((ROOT/PROTOCOL).read_text())
    for value in (data,protocol):
        if (value.get('scope')!='controlled_os_context_privacy_transaction_interleaving' or value.get('provider_kind')!='controlled_loopback_fixture'
                or value.get('actual_llm_or_gpu') is not False or value.get('app_turns')!=2 or value.get('expected_app_processes')!=2):raise ValueError('Race execution contract mismatch')
    if not source_paths()<=data.get('sha256',{}).keys():raise ValueError('Race source inputs missing')
    for name,value in data['sha256'].items():
        p=ROOT/name
        if not p.resolve().is_relative_to(ROOT) or digest(p)!=value:raise ValueError('Race source changed: '+name)
    return data
