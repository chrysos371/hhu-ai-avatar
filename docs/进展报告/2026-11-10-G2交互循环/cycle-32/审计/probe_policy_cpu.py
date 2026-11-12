"""Fake-owned-context order and rejection controls; no real model/GPU."""
from hashlib import sha256
import json
from pathlib import Path
from state_policy import apply_policy,POLICIES
BASE=Path(__file__).resolve().parents[1]


class Context:
    def __init__(self,events):self.memory=object();self.events=events
    def kv_cache_clear(self):self.events.append('clear')


class Model:
    def __init__(self):self.n_tokens=42;self.events=[];self._ctx=Context(self.events)
    def reset(self):self.events.append('reset');self.n_tokens=0


def main():
    rows=[]
    for policy,expected in zip(POLICIES,([],['reset'],['clear','reset'])):
        model=Model();result=apply_policy(model,policy);assert model.events==expected
        assert result['logical_tokens_before_policy']==42 and result['logical_tokens_after_policy']==(42 if policy=='reuse' else 0)
        assert result['explicit_logical_reset_called']==(policy!='reuse') and result['explicit_context_memory_clear_called']==(policy=='memory_clear_reset')
        rows.append({'control':policy,'events':model.events,'result':result,'passed':True})
    model=Model()
    try:apply_policy(model,'unsupported');raise AssertionError('Unknown policy accepted')
    except ValueError:assert model.n_tokens==42 and model.events==[]
    rows.append({'control':'unsupported_policy','rejected_before_mutation':True,'passed':True})
    model=Model();model._ctx.memory=None
    try:apply_policy(model,'memory_clear_reset');raise AssertionError('Missing context memory accepted')
    except RuntimeError:assert model.n_tokens==42 and model.events==[]
    rows.append({'control':'missing_owned_memory','rejected_before_mutation':True,'passed':True})
    class Broken(Model):
        def reset(self):self.events.append('broken_reset')
    model=Broken()
    try:apply_policy(model,'logical_reset');raise AssertionError('Broken reset claimed success')
    except RuntimeError:assert model.n_tokens==42
    rows.append({'control':'broken_reset','nonzero_counter_not_claimed_reset':True,'passed':True})
    out=BASE/'审计/工作目录/001-原生状态隔离/policy-cpu-controls.json';assert not out.exists()
    out.write_text(json.dumps({'passed':True,'actual_llm_or_gpu':False,'fake_owned_context':True,'helper_sha256':sha256(Path(__file__).read_bytes()).hexdigest(),'policy_sha256':sha256(Path(__file__).with_name('state_policy.py').read_bytes()).hexdigest(),'controls':rows},ensure_ascii=False,indent=2)+'\n')
    print('6 fake owned-context controls passed:exact call order/counters,unknown policy/missing memory/broken reset rejected;no actual LLM/GPU.')


if __name__=='__main__':main()
