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
def test_valid_new_registry_reaches_controlled_provider_boundary(tmp_path,monkeypatch,model):
    calls=[]
    def boundary(command,**kwargs):calls.append(command);raise BoundaryReached('controlled spawn; no GPU/model')
    monkeypatch.setattr(runner,'subprocess',SimpleNamespace(check_output=subprocess.check_output,Popen=boundary,STDOUT=subprocess.STDOUT))
    monkeypatch.setattr(runner,'gpu_snapshot',lambda:'controlled unused inventory')
    monkeypatch.setattr(runner,'gpu_processes',lambda:'')
    output=tmp_path/'owned-output';expected=sha256(REGISTRY.read_bytes()).hexdigest()
    with pytest.raises(BoundaryReached):runner.main(output,Path(sys.executable),protocol=PROTOCOL,model_key=model,
        registry_path=REGISTRY,expected_registry_sha256=expected)
    assert len(calls)==1 and output.exists();command=calls[0]
    assert command[command.index('--registry')+1]==str(REGISTRY)
    assert command[command.index('--expected-registry-sha256')+1]==expected
