"""Registry selection must be pinned before model/GPU construction."""
from hashlib import sha256
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import serve_local_model_eval as provider


def spec(key='qwen3-4b-q4_k_m'):
    return {'model_id':key,'file':'fixture.gguf','sha256':'a'*64,'revision':'b'*40,'required_free_mib':16384}


@pytest.fixture
def registries(tmp_path):
    old=tmp_path/'evals/interaction/cycle-02/model-scale-protocol.json';new=tmp_path/'evals/interaction/cycle-26/models.json'
    for p,models in [(old,[spec()]),(new,[spec(),spec('qwen3-32b-q4_k_m')])]:
        p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps({'models':models}))
    return tmp_path,old,new


def test_historical_default_remains_selectable_without_override(registries):
    root,old,_=registries
    data,pinned,path=provider.load_registry(None,root=root)
    assert data['models']==[spec()] and pinned==sha256(old.read_bytes()).hexdigest() and path==old


def test_explicit_new_registry_requires_and_preserves_raw_identity(registries):
    root,_,new=registries;expected=sha256(new.read_bytes()).hexdigest()
    data,pinned,path=provider.load_registry(new,expected_sha256=expected,root=root)
    assert len(data['models'])==2 and pinned==expected and path==new


def test_unpinned_override_is_rejected(registries):
    root,_,new=registries
    with pytest.raises(ValueError,match='requires expected registry SHA'):
        provider.load_registry(new,root=root)


def test_changed_registry_is_rejected_before_json_parse(registries):
    root,_,new=registries;expected=sha256(new.read_bytes()).hexdigest();new.write_text('{malformed')
    with pytest.raises(ValueError,match='Registry identity changed'):
        provider.load_registry(new,expected_sha256=expected,root=root)


@pytest.mark.parametrize('change',['duplicate','bad_hash','bad_revision','escaped_file','bool_memory','zero_memory','metadata_escape'])
def test_malformed_or_escaping_registry_cannot_authorize_a_model(registries,change):
    root,_,new=registries;model=spec()
    if change=='bad_hash':model['sha256']='unknown'
    elif change=='bad_revision':model['revision']='unknown'
    elif change=='escaped_file':model['file']='../fixture.gguf'
    elif change=='bool_memory':model['required_free_mib']=True
    elif change=='zero_memory':model['required_free_mib']=0
    elif change=='metadata_escape':model['metadata']='../outside.json'
    models=[model,model] if change=='duplicate' else [model]
    new.write_text(json.dumps({'models':models}));expected=sha256(new.read_bytes()).hexdigest()
    with pytest.raises(ValueError):provider.load_registry(new,expected_sha256=expected,root=root)


def test_external_registry_path_is_not_a_project_input(tmp_path,registries):
    root,_,_=registries;outside=root.parent/'external-model-registry.json';outside.write_text(json.dumps({'models':[spec()]}))
    with pytest.raises(ValueError,match='inside the project'):
        provider.load_registry(outside,expected_sha256=sha256(outside.read_bytes()).hexdigest(),root=root)


@pytest.mark.parametrize('change',['top_level','hash_type','revision_type'])
def test_wrong_json_types_are_rejected_before_gpu(registries,change):
    root,_,new=registries;model=spec()
    if change=='hash_type':model['sha256']=None
    if change=='revision_type':model['revision']=123
    new.write_text(json.dumps([] if change=='top_level' else {'models':[model]}))
    with pytest.raises(ValueError):provider.load_registry(new,expected_sha256=sha256(new.read_bytes()).hexdigest(),root=root)



def test_actual_default_registry_works_without_explicit_fixture_root():
    data,identity,path=provider.load_registry()
    assert path==provider.ROOT/'evals/interaction/cycle-02/model-scale-protocol.json'
    assert identity==sha256(path.read_bytes()).hexdigest()
    assert {m['model_id'] for m in data['models']}=={'qwen3-4b-q4_k_m','qwen3-14b-q4_k_m'}


def test_real_provider_cli_wrong_registry_sha_stops_before_model_or_output(tmp_path):
    import subprocess
    root=Path(__file__).resolve().parents[1]
    ready=tmp_path/'ready.json';trace=tmp_path/'trace.jsonl'
    command=[sys.executable,str(root/'scripts/serve_local_model_eval.py'),'--model',str(tmp_path/'absent.gguf'),
        '--model-key','qwen3-32b-q4_k_m','--metadata',str(root/'evals/interaction/cycle-26/model-metadata-32b.json'),
        '--registry',str(root/'evals/interaction/cycle-26/model-scale-registry.json'),'--expected-registry-sha256','changed',
        '--ready',str(ready),'--trace',str(trace)]
    result=subprocess.run(command,cwd=root,capture_output=True,text=True)
    assert result.returncode!=0 and 'Registry identity changed' in result.stderr
    assert not ready.exists() and not trace.exists()
