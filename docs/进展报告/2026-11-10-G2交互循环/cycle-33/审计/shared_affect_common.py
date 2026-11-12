"""Committed source identity for shared actual-history affect diagnosis."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[5];BASE=Path(__file__).resolve().parents[1]
OLD31=BASE.parent/'cycle-31/审计';OLD32=BASE.parent/'cycle-32/审计'
sys.path.insert(0,str(OLD31))
from analysis_cost_common import source_paths as old_paths,require_loopback,runtime_modules
sys.path.insert(0,str(OLD32))
from state_common import digest,verify_historical_binding,verify_backend,RUNTIME
PROTOCOL='evals/interaction/cycle-33/implicit-affect-protocol.json'
REGISTRY='evals/interaction/cycle-26/model-scale-registry.json'
MODELS=('qwen3-4b-q4_k_m','qwen3-32b-q4_k_m');ARMS=('current_analysis','lab_readonly_candidate')


def source_paths():
    paths=old_paths()|{PROTOCOL,RUNTIME,'evals/interaction/cycle-31/readonly-affect-whitebox-supplement.json'}
    paths.update(str((OLD32/name).relative_to(ROOT)) for name in ('state_common.py','state_policy.py','serve_state_eval.py','证据清单.json'))
    paths.update(str((BASE/'审计'/name).relative_to(ROOT)) for name in ('shared_affect_common.py','shared_affect_worker.py','shared_snapshot.py','probe_shared_cpu.py','run_shared_affect.py'))
    paths.update(str((BASE/'审计/工作目录/001-共享历史隐含情绪'/name).relative_to(ROOT)) for name in ('shared-cpu-controls.json','shared-cpu-controls.log','cpu-control-version.json'))
    return paths


def verify_freeze(path,expected,model=None):
    if digest(path)!=expected:raise ValueError('Shared affect freeze identity changed')
    frozen=json.loads(Path(path).read_text());protocol=json.loads((ROOT/PROTOCOL).read_text())
    contract={'scope':'actual_native_web_shared_snapshot_implicit_affect_diagnostic','backend':'cuda','models':list(MODELS),'arms':list(ARMS),'repetitions':3,
        'provider_policy':'logical_reset','shared_preparation_groups_per_model':48,'app_turns_per_model':192,'expected_app_processes_per_model':144,
        'probe_pairs_per_model':48,'implicit_pairs_per_model':36,'neutral_pairs_per_model':12,'max_model_http_calls_per_model':386,'min_model_http_calls_per_model':338,
        'production_activation_authorized':False,'prospective_execution_authorized':False,'latency_benefit_claim_authorized':False,'general_semantic_approval':False}
    for data in (frozen,protocol):
        for key,value in contract.items():
            if data.get(key)!=value:raise ValueError('Shared affect execution contract differs: '+key)
    if model is not None and model not in MODELS:raise ValueError('Unexpected shared affect model')
    cases=protocol['cases'];assert len(cases)==16 and len({c['id'] for c in cases})==16 and sum(c['stratum']=='implicit_affect' for c in cases)==12
    assert all(len(c['shared_preparation'])==2 and c['expected_code']=='AB-2738' and c['candidate_route_not_assumed'] is True for c in cases)
    assert protocol['warmups']==[False,True] and len(protocol['case_arm_orders'])==3 and all(len(order)==16 and all(sorted(pair)==sorted(ARMS) for pair in order) for order in protocol['case_arm_orders'])
    assert digest(ROOT/protocol['source_whitebox_path'])==protocol['source_whitebox_sha256'] and digest(ROOT/RUNTIME)==protocol['backend_runtime_identity_sha256']
    if not source_paths()<=frozen.get('sha256',{}).keys():raise ValueError('Shared affect source inputs missing')
    for name,value in frozen['sha256'].items():
        target=ROOT/name
        if not target.resolve().is_relative_to(ROOT) or digest(target)!=value:raise ValueError('Shared affect source changed: '+name)
    return frozen
