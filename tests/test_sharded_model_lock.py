import json
from pathlib import Path
import pytest
from avatar.lab import runner


@pytest.mark.parametrize('has_index', [False, True])
def test_sharded_lock_requires_and_retains_index_provenance(tmp_path, monkeypatch, has_index):
    config=json.loads((Path(__file__).resolve().parents[1]/'experiments/style/models.json').read_text())
    config['models']=config['models'][:1]
    source=tmp_path/'models.json';source.write_text(json.dumps(config))
    siblings=[{'rfilename':f'model-{n:05d}-of-00002.safetensors', 'lfs':{'sha256':'a'*64,'size':20}}
              for n in [1,2]]
    siblings += [{'rfilename':name,'size':10,'blobId':'b'*40}
                 for name in ['config.json','tokenizer.json','tokenizer_config.json']]
    if has_index:
        siblings.append({'rfilename':'model.safetensors.index.json','size':88,'blobId':'c'*40})
    monkeypatch.setattr(runner,'get_json',lambda url:{'sha':'d'*40,'siblings':siblings})
    def output(path):path.mkdir();return path
    monkeypatch.setattr(runner,'new_output',output)
    runner.lock_models(source,tmp_path/'lock')
    model=json.loads((tmp_path/'lock/models.lock.json').read_text())['models'][0]
    if has_index:
        assert model['status']=='locked'
        index=next(a for a in model['assets'] if a['path']=='model.safetensors.index.json')
        assert index['git_blob_sha1']=='c'*40 and index['bytes']==88
    else:
        assert model['status']=='unavailable' and model['error_type']=='ValueError'
