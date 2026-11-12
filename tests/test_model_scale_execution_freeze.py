"""Current-default model scale freezes must pin descriptor and all runtime sources."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import evaluate_native_output_audit as audit
import run_native_output_models as runner
from test_native_sampler_registry import ready
ROOT=Path(__file__).resolve().parents[1]
PROTOCOL=ROOT/'evals/interaction/cycle-26/current-default-model-scale-protocol.json'
REGISTRY=ROOT/'evals/interaction/cycle-26/model-scale-registry.json'


def frozen(path,models=None):
    protocol=json.loads(PROTOCOL.read_text());names=set(audit.fingerprint(PROTOCOL))|{'scripts/run_native_output_models.py'}
    data={'scope':'native_current_defaults_model_scale','candidate':'none','execution_authorized':True,
        'allowed_partition':'development','provider_backend':'cuda','protocol':str(PROTOCOL.relative_to(ROOT)),
        'models_registry':str(REGISTRY.relative_to(ROOT)),'registry_sha256':sha256(REGISTRY.read_bytes()).hexdigest(),
        'models':models or [m['model_id'] for m in json.loads(REGISTRY.read_text())['models']],
        'case_ids':[c['id'] for c in protocol['cases']],'case_count':len(protocol['cases']),
        'turn_count':sum(len(c['turns']) for c in protocol['cases']),
        'sha256':{name:sha256((ROOT/name).read_bytes()).hexdigest() for name in names}}
    path.write_text(json.dumps(data,indent=2));return data,sha256(path.read_bytes()).hexdigest()


def test_valid_current_defaults_freeze_binds_real_sources(tmp_path):
    path=tmp_path/'freeze.json';data,expected=frozen(path)
    assert audit.verify_execution_freeze(path,expected,PROTOCOL,model_id='qwen3-32b-q4_k_m')==data


def test_descriptor_identity_precedes_json_parsing(tmp_path):
    path=tmp_path/'freeze.json';_,expected=frozen(path);path.write_text('{malformed')
    with pytest.raises(ValueError,match='Execution freeze descriptor identity changed'):
        audit.verify_execution_freeze(path,expected,PROTOCOL,model_id='qwen3-4b-q4_k_m')


@pytest.mark.parametrize('change',['input_hash','missing_input','scope','backend','partition','candidate','model','case_order','turn_count','registry'])
def test_incomplete_or_wrong_execution_contract_is_rejected(tmp_path,change):
    path=tmp_path/'freeze.json';data,_=frozen(path)
    if change=='input_hash':data['sha256']['src/avatar/main.py']='0'*64
    elif change=='missing_input':data['sha256'].pop('src/avatar/main.py')
    elif change=='scope':data['scope']='some_other_job'
    elif change=='backend':data['provider_backend']='cpu_explicit'
    elif change=='partition':data['allowed_partition']='prospective'
    elif change=='candidate':data['candidate']='lab-v4'
    elif change=='model':data['models']=['qwen3-4b-q4_k_m']
    elif change=='case_order':data['case_ids']=list(reversed(data['case_ids']))
    elif change=='turn_count':data['turn_count']+=1
    else:data['registry_sha256']='changed'
    path.write_text(json.dumps(data));expected=sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError):audit.verify_execution_freeze(path,expected,PROTOCOL,model_id='qwen3-32b-q4_k_m')


@pytest.mark.parametrize('entry',['runner','sampler'])
def test_real_os_entry_wrong_descriptor_sha_rejects_before_output_or_model(tmp_path,entry):
    freeze=tmp_path/'freeze.json';_,expected=frozen(freeze);freeze.write_text(freeze.read_text()+'\n')
    output=tmp_path/'must-not-exist'
    command=[sys.executable,str(ROOT/'scripts'/('run_native_output_models.py' if entry=='runner' else 'evaluate_native_output_audit.py')),
        '--protocol',str(PROTOCOL),'--output',str(output),'--execution-freeze',str(freeze),'--expected-execution-freeze-sha256',expected]
    if entry=='runner':command+=['--stage','development','--provider-python',sys.executable,'--model-key','qwen3-32b-q4_k_m',
        '--registry',str(REGISTRY),'--expected-registry-sha256',sha256(REGISTRY.read_bytes()).hexdigest()]
    else:
        provider,_=ready();path=tmp_path/'provider.json';path.write_text(json.dumps(provider));command+=['--provider',str(path)]
    result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
    assert result.returncode!=0 and 'Execution freeze descriptor identity changed' in result.stderr
    assert not output.exists()


@pytest.mark.parametrize('mutate',[False,True])
def test_freeze_checked_between_controlled_warmups_before_application_server(tmp_path,monkeypatch,mutate):
    freeze=tmp_path/'freeze.json';data,expected=frozen(freeze);provider,_=ready();path=tmp_path/'provider.json';path.write_text(json.dumps(provider))
    warm=[];servers=[]
    class Boundary(RuntimeError):pass
    class Engine:
        def __init__(self,*args,**kwargs):pass
        def chat(self,*args,**kwargs):
            warm.append('sync')
            if mutate:data['scope']='changed_after_first_warmup';freeze.write_text(json.dumps(data))
            return 'controlled warmup'
        def stream_chat(self,*args,**kwargs):warm.append('stream');return 'controlled warmup'
        def close(self):pass
    def server(*args,**kwargs):servers.append(True);raise Boundary('controlled application server boundary')
    monkeypatch.setattr(audit,'LLMEngine',Engine);monkeypatch.setattr(audit,'create_server',server)
    for obj,field in ((audit.config.llm,'base_url'),(audit.config.llm,'api_key'),(audit.config.llm,'model'),(audit.config.embedding,'model')):
        monkeypatch.setattr(obj,field,getattr(obj,field))
    report=audit.evaluate(path,tmp_path/'owned-output',PROTOCOL,execution_freeze=freeze,expected_execution_freeze_sha256=expected)
    assert report['executionFreezeSha256']==expected and not report['engineering_passed']
    if mutate:assert warm==['sync'] and servers==[] and 'descriptor identity changed' in report['failure']
    else:assert warm==['sync','stream'] and len(servers)==1 and 'controlled application server boundary' in report['failure']
