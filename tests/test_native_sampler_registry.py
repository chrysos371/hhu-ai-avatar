"""C26 sampler admission uses no model/network; runtime-path child uses --help."""
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import evaluate_native_output_audit as audit
ROOT=Path(__file__).resolve().parents[1]
PROTOCOL=ROOT/'evals/interaction/cycle-26/current-default-model-scale-protocol.json'
REGISTRY=ROOT/'evals/interaction/cycle-26/model-scale-registry.json'


def ready():
    protocol=json.loads(PROTOCOL.read_text());registry=json.loads(REGISTRY.read_text());model=registry['models'][-1]
    return {'url':'http://127.0.0.1:1/v1','model_id':model['model_id'],'model_sha256':model['sha256'],
        'model_revision':model['revision'],'registry_sha256':sha256(REGISTRY.read_bytes()).hexdigest(),
        'registry_path':str(REGISTRY.relative_to(ROOT)),'metadata_path':str(ROOT/model['metadata']),
        'metadata_sha256':sha256((ROOT/model['metadata']).read_bytes()).hexdigest(),
        'backend':'cuda','chosen_gpu':{'index':0,'uuid':'GPU-controlled-fixture','free_mib':40441,'utilization_percent':0},
        'process_gpu_mib_after_load':[25000],'effective_visible_devices':'GPU-controlled-fixture',
        'configuration':dict(protocol['inference'],n_gpu_layers=-1)},protocol


def test_new_registry_provider_contract_is_accepted_without_inference():
    provider,protocol=ready();model,binding=audit.validate_provider_identity(provider,protocol)
    assert model['model_id']=='qwen3-32b-q4_k_m'
    assert binding['registry_sha256']==sha256(REGISTRY.read_bytes()).hexdigest()
    assert binding['metadata_sha256']==provider['metadata_sha256']


@pytest.mark.parametrize('field',['registry_sha256','registry_path','model_sha256','model_revision',
    'metadata_sha256','metadata_path','backend','chosen_gpu','process_gpu_mib_after_load','effective_visible_devices','model_id'])
def test_new_registry_rejects_runtime_mismatch(field):
    provider,protocol=ready();provider[field]=None if field=='chosen_gpu' else ('changed' if field!='process_gpu_mib_after_load' else [])
    with pytest.raises(ValueError):audit.validate_provider_identity(provider,protocol)


@pytest.mark.parametrize('change',['missing_registry_pin','wrong_registry_pin','cpu_layers','missing_metadata_sha'])
def test_declared_contract_requires_pin_metadata_and_gpu_offload(change):
    provider,protocol=ready()
    if change=='missing_registry_pin':protocol.pop('models_registry_sha256')
    elif change=='wrong_registry_pin':protocol['models_registry_sha256']='changed'
    elif change=='cpu_layers':provider['configuration']['n_gpu_layers']=0
    else:provider.pop('metadata_sha256')
    with pytest.raises(ValueError):audit.validate_provider_identity(provider,protocol)


def test_legacy_default_registry_minimal_metadata_remains_explicitly_compatible():
    protocol=json.loads((ROOT/'evals/interaction/cycle-19/capability-output-protocol.json').read_text())
    model=json.loads((ROOT/protocol['models_registry']).read_text())['models'][0]
    provider={'url':'http://127.0.0.1:1/v1','model_id':model['model_id'],'model_sha256':model['sha256'],
              'model_revision':model['revision'],'configuration':protocol['inference']}
    selected,_=audit.validate_provider_identity(provider,protocol);assert selected['model_id']==model['model_id']


def test_fingerprint_includes_selected_registry_and_all_declared_metadata():
    fields=audit.fingerprint(PROTOCOL);assert str(REGISTRY.relative_to(ROOT)) in fields
    for model in json.loads(REGISTRY.read_text())['models']:assert model['metadata'] in fields


def test_runtime_source_identity_is_actual_project_modules():
    identity=audit.runtime_source_identity()
    for name in ('avatar.web','avatar.brain.memory','avatar.brain.llm'):
        value=identity[name];path=Path(value['path']);assert path.is_relative_to(ROOT/'src')
        assert value['sha256']==sha256(path.read_bytes()).hexdigest()


def test_wrong_provider_rejected_before_output_or_engine(tmp_path,monkeypatch):
    provider,_=ready();provider['metadata_sha256']='changed';path=tmp_path/'provider.json';path.write_text(json.dumps(provider))
    def forbidden(*args,**kwargs):raise AssertionError('Model boundary must not be reached')
    for obj, field in ((audit.config.llm,'base_url'),(audit.config.llm,'api_key'),(audit.config.llm,'model'),(audit.config.embedding,'model')):
        monkeypatch.setattr(obj,field,getattr(obj,field))
    monkeypatch.setattr(audit,'LLMEngine',forbidden);output=tmp_path/'must-not-exist'
    with pytest.raises(ValueError):audit.evaluate(path,output,PROTOCOL)
    assert not output.exists()


def test_real_cli_prefers_own_source_over_foreign_pythonpath(tmp_path):
    foreign=tmp_path/'foreign-src/avatar';foreign.mkdir(parents=True);(foreign/'__init__.py').write_text('raise RuntimeError("foreign avatar selected")\n')
    env=dict(os.environ,PYTHONPATH=str(foreign.parent))
    result=subprocess.run([sys.executable,str(ROOT/'scripts/evaluate_native_output_audit.py'),'--help'],
                          cwd=ROOT,env=env,capture_output=True,text=True)
    assert result.returncode==0 and '--provider' in result.stdout and 'foreign avatar selected' not in result.stderr



def test_cached_foreign_module_cannot_be_claimed_as_current_project(tmp_path,monkeypatch):
    path=tmp_path/'foreign_llm.py';path.write_text('# foreign fixture only\n')
    monkeypatch.setattr(sys.modules['avatar.brain.llm'],'__file__',str(path))
    with pytest.raises(ValueError,match='imported outside this project'):audit.runtime_source_identity()
