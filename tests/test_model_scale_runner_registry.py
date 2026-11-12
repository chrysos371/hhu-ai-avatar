"""New registry admission stops before owned output/model dispatch on mismatch."""
from hashlib import sha256
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_native_output_models as runner
ROOT=Path(__file__).resolve().parents[1]
REGISTRY=ROOT/'evals/interaction/cycle-26/model-scale-registry.json'
PROTOCOL=ROOT/'evals/interaction/cycle-26/current-default-model-scale-protocol.json'
OLD_PROTOCOL=ROOT/'evals/interaction/cycle-19/capability-output-protocol.json'


class BoundaryReached(RuntimeError):pass


@pytest.mark.parametrize('change',['no_sha','wrong_sha','protocol_mismatch','implicit_old','capability_override','unknown_model'])
def test_bad_registry_contract_rejected_before_output_or_provider(tmp_path,change):
    output=tmp_path/'must-not-exist'
    options={'registry_path':REGISTRY,'expected_registry_sha256':sha256(REGISTRY.read_bytes()).hexdigest(),
             'protocol':PROTOCOL,'model_key':'qwen3-32b-q4_k_m'}
    if change=='no_sha':options['expected_registry_sha256']=None
    elif change=='wrong_sha':options['expected_registry_sha256']='changed'
    elif change=='protocol_mismatch':options['protocol']=OLD_PROTOCOL
    elif change=='implicit_old':options['registry_path']=None;options['expected_registry_sha256']=None
    elif change=='capability_override':options['stage']='capability_pair'
    elif change=='unknown_model':options['model_key']='unknown-model'
    with pytest.raises(ValueError):runner.main(output,Path(sys.executable),**options)
    assert not output.exists()


@pytest.mark.parametrize('model',['qwen3-4b-q4_k_m','qwen3-32b-q4_k_m'])
@pytest.mark.parametrize('relative',[False,True])
def test_valid_new_registry_reaches_controlled_provider_boundary(tmp_path,monkeypatch,model,relative):
    monkeypatch.chdir(ROOT)
    calls=[]
    def boundary(command,**kwargs):calls.append(command);raise BoundaryReached('controlled spawn; no GPU/model')
    monkeypatch.setattr(runner,'subprocess',SimpleNamespace(check_output=subprocess.check_output,Popen=boundary,STDOUT=subprocess.STDOUT))
    monkeypatch.setattr(runner,'gpu_snapshot',lambda:'controlled unused inventory')
    monkeypatch.setattr(runner,'gpu_processes',lambda:'')
    output=tmp_path/'owned-output';expected=sha256(REGISTRY.read_bytes()).hexdigest()
    from test_model_scale_execution_freeze import frozen
    freeze=tmp_path/'execution.json';_,pinned=frozen(freeze)
    selected_protocol=Path(PROTOCOL.relative_to(ROOT)) if relative else PROTOCOL
    with pytest.raises(BoundaryReached):runner.main(output,Path(sys.executable),protocol=selected_protocol,model_key=model,
        registry_path=REGISTRY,expected_registry_sha256=expected,execution_freeze=freeze,expected_execution_freeze_sha256=pinned)
    assert len(calls)==1 and output.exists();command=calls[0]
    assert command[command.index('--registry')+1]==str(REGISTRY)
    assert command[command.index('--expected-registry-sha256')+1]==expected



@pytest.mark.parametrize('pin',[None,'changed'])
def test_selected_protocol_must_pin_new_registry(tmp_path,pin):
    import json
    data=json.loads(PROTOCOL.read_text())
    if pin is None:data.pop('models_registry_sha256')
    else:data['models_registry_sha256']=pin
    protocol=tmp_path/'protocol.json';protocol.write_text(json.dumps(data));output=tmp_path/'must-not-exist'
    with pytest.raises(ValueError,match='pinned protocol identity'):
        runner.main(output,Path(sys.executable),protocol=protocol,model_key='qwen3-32b-q4_k_m',
                    registry_path=REGISTRY,expected_registry_sha256=sha256(REGISTRY.read_bytes()).hexdigest())
    assert not output.exists()
