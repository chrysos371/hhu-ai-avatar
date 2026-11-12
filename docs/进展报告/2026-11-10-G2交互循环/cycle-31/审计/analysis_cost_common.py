"""Frozen audit-only repeated read-only analysis cost contract."""
from hashlib import sha256
import io
import json
from pathlib import Path
import subprocess
import tarfile
import sys
ROOT=Path(__file__).resolve().parents[5];BASE=Path(__file__).resolve().parents[1]
OLD30=BASE.parent/'cycle-30/审计'
sys.path.insert(0,str(OLD30))
from context_native_common import source_paths as old_source_paths,require_loopback,runtime_modules
PROTOCOL='evals/interaction/cycle-31/readonly-analysis-cost-protocol.json'
CPU='evals/interaction/cycle-31/readonly-analysis-cpu-controls.json'
REGISTRY='evals/interaction/cycle-26/model-scale-registry.json'
MODELS=('qwen3-4b-q4_k_m','qwen3-32b-q4_k_m');ARMS=('current_analysis','lab_readonly_candidate')


def digest(path):return sha256(Path(path).read_bytes()).hexdigest()


def source_paths():
    result=old_source_paths()|{PROTOCOL,CPU}
    result.update(str((BASE/'审计'/n).relative_to(ROOT)) for n in ('readonly_analysis_candidate.py','probe_readonly_cpu.py','probe_readonly_web_cpu.py','analysis_cost_common.py','analysis_cost_worker.py','run_readonly_analysis_cost.py'))
    result.update(str((BASE/'审计/工作目录/001-只读分析路由保护'/n).relative_to(ROOT)) for n in ('shadow-v1.json','shadow-v1.log','cpu-web-controls-v1.json','cpu-web-controls-v1.log','cpu-control-versions.json'))
    return result


def verify_freeze(path,expected,model=None):
    if digest(path)!=expected:raise ValueError('Readonly analysis freeze identity changed')
    data=json.loads(Path(path).read_text());protocol=json.loads((ROOT/PROTOCOL).read_text())
    for value in (data,protocol):
        if (value.get('scope')!='lab_readonly_analysis_cost_shadow_and_native_development' or value.get('backend')!='cuda'
                or value.get('models')!=list(MODELS) or value.get('arms')!=list(ARMS) or value.get('repetitions')!=3
                or value.get('app_turns_per_model')!=144 or value.get('expected_app_processes_per_model')!=96
                or value.get('expected_model_http_calls_per_model')!=272 or value.get('max_model_http_calls_per_model')!=290
                or value.get('production_activation_authorized') is not False or value.get('prospective_execution_authorized') is not False):raise ValueError('Readonly execution contract mismatch')
    if model is not None and model not in MODELS:raise ValueError('Unexpected readonly model')
    if len(protocol.get('cases',[]))!=8 or sum(c['candidate_probe_eligible'] for c in protocol['cases'])!=6:raise ValueError('Readonly case schedule changed')
    if len(protocol.get('case_arm_orders',[]))!=3 or any(len(orders)!=8 or any(sorted(order)!=sorted(ARMS) for order in orders) for orders in protocol['case_arm_orders']):raise ValueError('Readonly arm schedule changed')
    if not source_paths()<=data.get('sha256',{}).keys():raise ValueError('Readonly frozen sources missing')
    for name,value in data['sha256'].items():
        target=ROOT/name
        if not target.resolve().is_relative_to(ROOT) or digest(target)!=value:raise ValueError('Readonly source changed: '+name)
    return data


def verify_historical_binding(value):
    raw=subprocess.check_output(['git','archive','--format=tar',value['source_ref'],'--',*sorted(value['sha256'])],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as archive:
        actual={member.name:sha256(archive.extractfile(member).read()).hexdigest() for member in archive.getmembers() if member.isfile()}
    if actual!=value['sha256']:raise ValueError('Readonly historical source identity mismatch')
    return True
