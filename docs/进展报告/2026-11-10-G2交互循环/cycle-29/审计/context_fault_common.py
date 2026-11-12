"""Explicit source contract for eight controlled OS context fault workflows."""
import json
from context_baseline_common import ROOT,BASE,digest,require_loopback,runtime_modules
PROTOCOL='evals/interaction/cycle-29/context-fault-controls-protocol.json'
CASES=['privacy_crosssession','scope','cancel','corrupt_result','mixed_writer','bounded_window','no_old_actions','optout']


def source_paths():
    paths={PROTOCOL}
    paths.update(str(p.relative_to(ROOT)) for g in ('src','scripts') for p in (ROOT/g).rglob('*.py'))
    paths.update(str((BASE/'审计'/n).relative_to(ROOT)) for n in ('context_baseline_common.py','run_context_baseline.py','context_fault_common.py','context_fault_worker.py','run_context_fault_controls.py'))
    return paths


def verify_freeze(path,expected):
    if digest(path)!=expected:raise ValueError('Fault freeze identity changed')
    data=json.loads(path.read_text());protocol=json.loads((ROOT/PROTOCOL).read_text())
    for obj in (data,protocol):
        if (obj.get('scope')!='actual_http_os_context_fault_controls' or obj.get('provider_kind')!='controlled_loopback_fixture'
                or obj.get('actual_llm_or_gpu') is not False or obj.get('case_ids')!=CASES
                or obj.get('app_turns')!=45 or obj.get('expected_app_processes')!=20):raise ValueError('Unexpected fault protocol')
    if not source_paths()<=data.get('sha256',{}).keys():raise ValueError('Fault source inputs missing')
    for name,value in data['sha256'].items():
        p=ROOT/name
        if not p.resolve().is_relative_to(ROOT) or digest(p)!=value:raise ValueError('Fault input changed: '+name)
    return data
