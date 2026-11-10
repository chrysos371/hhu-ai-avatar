import importlib.util
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
spec=importlib.util.spec_from_file_location('review_experiment',ROOT/'scripts/evaluate_response_review.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def test_invalid_warmup_is_preserved_and_does_not_drop_fixed_cases(tmp_path, monkeypatch):
    registry=json.loads((ROOT/'evals/interaction/cycle-02/model-scale-protocol.json').read_text())['models'][0]
    provider=tmp_path/'provider.json'
    provider.write_text(json.dumps(dict(url='http://127.0.0.1:1/v1',model_id=registry['model_id'],
        model_sha256=registry['sha256'],model_revision=registry['revision'],
        configuration=dict(temperature=0,seed=42,thinking=False))))
    suite=tmp_path/'suite.json'
    suite.write_text(json.dumps(dict(models=[registry['model_id']],inference=dict(temperature=0,seed=42,thinking=False),
        cases=[dict(id='actual-case',split='development',user_text='你好',draft='你好',verified_profile={},
            expected_verdict='pass',expected_category='none')]))))
    class Engine:
        def __init__(self,**kwargs):self.calls=0
        def review_response(self,*args,**kwargs):
            self.calls+=1
            return '{}' if self.calls==1 else json.dumps(dict(verdict='pass',category='none',quote='',reason='未发现两类问题'))
        def close(self):pass
    output=tmp_path/'result.json'
    monkeypatch.setattr(module,'LLMEngine',Engine)
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(sys,'argv',['evaluate_response_review.py','--provider',str(provider),'--suite',str(suite),'--output',str(output)])
    module.main()
    result=json.loads(output.read_text())
    assert result['warmup']['valid'] is False
    assert result['warmup']['raw_judgment']=='{}'
    assert result['execution_complete'] and len(result['rows'])==1
    assert result['rows'][0]['id']=='actual-case'
    assert result['production_activation_approved'] is False
