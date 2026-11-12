"""Phase-specific committed source contract for native emotion revision regression."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[5];BASE=Path(__file__).resolve().parents[1]
OLD33=BASE.parent/'cycle-33/审计';OLD32=BASE.parent/'cycle-32/审计'
sys.path.insert(0,str(OLD33))
from shared_affect_common import source_paths as old_paths,require_loopback,runtime_modules,digest,verify_historical_binding,verify_backend,RUNTIME
PROTOCOL='evals/interaction/cycle-34/emotion-revision-protocol.json';REGISTRY='evals/interaction/cycle-26/model-scale-registry.json'
MODELS=('qwen3-4b-q4_k_m','qwen3-32b-q4_k_m');PHASES=('before','after')


def source_paths(phase):
    paths=old_paths()|{PROTOCOL,str((OLD33/'证据清单.json').relative_to(ROOT))}
    paths.update(str((BASE/'审计'/name).relative_to(ROOT)) for name in ('revision_common.py','revision_worker.py','probe_revision_http.py','run_native_revision.py'))
    paths.update(str((BASE/'审计/工作目录/001-自动情绪版本失效'/name).relative_to(ROOT)) for name in ('controlled-http-before.json','controlled-http-before.log','before-control-version.json'))
    if phase=='after':
        paths.update(str((BASE/'审计/工作目录/001-自动情绪版本失效'/name).relative_to(ROOT)) for name in ('controlled-http-after.json','controlled-http-after.log','after-control-version.json'))
        paths.update(str((BASE/'审计/工作目录/002-系统回归'/name).relative_to(ROOT)) for name in ('full-python-binding.json','default-browser-binding.json'))
    return paths


def verify_freeze(path,expected,model=None,*,phase):
    if digest(path)!=expected:raise ValueError('Emotion revision freeze identity changed')
    frozen=json.loads(Path(path).read_text());protocol=json.loads((ROOT/PROTOCOL).read_text())
    if phase not in PHASES or frozen.get('phase')!=phase:raise ValueError('Emotion revision phase mismatch')
    contract={'scope':'automatic_emotion_privacy_revision_invalidation_engineering_regression','native_models':list(MODELS),
        'native_expected_calls_per_model_phase':8,'native_app_turns_per_model_phase':4,'native_app_os_per_model_phase':1,
        'native_warmups':[False,True],'native_state_policy':'logical_reset','production_candidate_activation_authorized':False,
        'cross_os_emotion_persistence_in_scope':False,'cancel_rollback_in_scope':False,'manual_override_deletion_in_scope':False}
    for data in (protocol,frozen):
        for key,value in contract.items():
            if data.get(key)!=value:raise ValueError('Emotion revision contract differs: '+key)
    if model is not None and model not in MODELS:raise ValueError('Unexpected emotion revision model')
    if len(protocol['native_fixed_source'])!=2 or len(protocol['native_after_forget_turns'])!=2:raise ValueError('Emotion revision task schedule differs')
    if not source_paths(phase)<=frozen.get('sha256',{}).keys():raise ValueError('Emotion revision source inputs missing')
    for name,value in frozen['sha256'].items():
        target=ROOT/name
        if not target.resolve().is_relative_to(ROOT) or digest(target)!=value:raise ValueError('Emotion revision source changed: '+name)
    if phase=='after':
        for name in ('full-python-binding.json','default-browser-binding.json'):
            binding=json.loads((BASE/'审计/工作目录/002-系统回归'/name).read_text())
            if binding.get('exit_code')!=0 or binding.get('source_unchanged') is not True:raise ValueError('After phase requires completed stable product checks')
    return frozen
