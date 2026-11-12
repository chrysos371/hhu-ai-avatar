"""Research authorization, output schedule and raw evidence integrity controls."""
from copy import deepcopy
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import probe_native_evidence_plans as runner


@pytest.fixture
def protocol():return json.loads((ROOT/runner.PROTOCOL).read_text())


def test_frozen_protocol_gold_is_not_any_wire_content(protocol):
    runner.validate_protocol(protocol)
    for case in protocol['cases']:
        plain=runner.payload(case,'plain');typed=runner.payload(case,'plan')
        assert plain['messages']==typed['messages']
        assert json.loads(plain['messages'][-1]['content'])=={'question':case['question'],'context':case['context']}
        assert 'gold' not in json.loads(typed['messages'][-1]['content'])


@pytest.mark.parametrize('key,value',[('scope','wrong'),('backend','cpu'),('registry','old'),('models',['qwen3-14b-q4_k_m']),('production_activation_authorized',True),('prospective_execution_authorized',True),('gold_sent_to_model',True),('same_messages_between_arms',False),('diagnostic_requests_per_model',25),('warmups',[0,1])])
def test_protocol_does_not_silently_ignore_execution_contract(protocol,key,value):
    protocol[key]=value
    with pytest.raises(ValueError):runner.validate_protocol(protocol)


def rows(protocol):
    out=[]
    for i,stream in enumerate(protocol['warmups']):
        out.append({'role':'warmup','warmup_index':i,'request':{'model':runner.MODELS[0],'messages':[{'role':'user','content':'请回答：你好。'}],'stream':stream,'temperature':0,'max_tokens':16},'reply':'你好','finish_reason':'stop'})
    for case,order in zip(protocol['cases'],protocol['arm_orders']):
        for arm in order:
            value={'role':'source_atom_diagnostic','case':case['id'],'arm':arm,'request':runner.payload(case,arm,runner.MODELS[0]),'reply':json.dumps(case['gold'],ensure_ascii=False) if arm=='plan' else 'fixture','finish_reason':'stop'}
            if arm=='plan':value.update(runner.grade_plan(value['reply'],case))
            out.append(value)
    return out


def test_complete_schedule_matches_raw_recomputed_plan_grades(protocol):
    runner.validate_rows(rows(protocol),protocol,runner.MODELS[0])


@pytest.mark.parametrize('change',['missing','order','finish','gold_leak','grade'])
def test_schedule_not_replaceable_by_self_reported_engineering_flags(protocol,change):
    values=rows(protocol)
    if change=='missing':values.pop()
    elif change=='order':values[2],values[3]=values[3],values[2]
    elif change=='finish':values[2]['finish_reason']='length'
    elif change=='gold_leak':values[2]['request']['messages'][-1]['content']+=' HIDDEN GOLD'
    else:next(r for r in values if r.get('arm')=='plan')['plan_exact']=False
    with pytest.raises(ValueError):runner.validate_rows(values,protocol,runner.MODELS[0])


def test_wrong_but_valid_source_is_a_scored_failure_not_a_rejection(protocol):
    case=next(c for c in protocol['cases'] if c['id']=='body_only');value={'operation':'copy_draft','reference':'a28','actor':'user'}
    result=runner.grade_plan(json.dumps(value),case)
    assert result['declared_schema_valid'] and result['render_passed']
    assert not result['plan_exact'] and not result['rendered_task_exact']


@pytest.mark.parametrize('entry',['probe_native_evidence_plans.py'])
def test_actual_os_wrong_descriptor_sha_fails_before_output_model_or_cuda(tmp_path,entry):
    frozen=tmp_path/'bad.json';frozen.write_text('{invalid')
    output=tmp_path/'must-not-exist'
    command=[sys.executable,str(ROOT/'scripts'/entry),'--model',runner.MODELS[0],'--output',str(output),'--freeze',str(frozen),'--expected-freeze-sha256','0'*64,'--provider-python',sys.executable]
    actual=subprocess.run(command,capture_output=True,text=True,cwd=ROOT)
    assert actual.returncode!=0 and 'Freeze descriptor identity changed' in actual.stderr
    assert not output.exists()


@pytest.fixture
def frozen(tmp_path):
    for name in runner.required_paths(tmp_path):
        path=tmp_path/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('fixture')
    inputs={name:runner.digest(tmp_path/name) for name in runner.required_paths(tmp_path)}
    value={'scope':'standalone_native_source_atom_content_diagnostic','backend':'cuda','protocol':runner.PROTOCOL,'models':list(runner.MODELS),'production_activation_authorized':False,'prospective_execution_authorized':False,'diagnostic_requests_per_model':24,'sha256':inputs}
    path=tmp_path/'freeze.json';path.write_text(json.dumps(value));return tmp_path,path,value


def test_source_freeze_positive_and_mutated_input_negative(frozen):
    root,path,value=frozen;expected=runner.digest(path)
    assert runner.verify_freeze(path,expected,runner.MODELS[0],root)==value
    (root/'scripts/native_evidence_plan.py').write_text('mutated')
    with pytest.raises(ValueError,match='Frozen input changed'):runner.verify_freeze(path,expected,runner.MODELS[0],root)


def test_no_prior_evidence_does_not_allow32b_launch():
    with pytest.raises(ValueError,match='pinned completed4B'):runner.prior_gate(None,'freeze',None)


@pytest.mark.parametrize('forged_schema',[False,True])
def test_prior_gate_recomputes_actual_rows_instead_of_trusting_flags(tmp_path,protocol,forged_schema):
    values=rows(protocol)
    if forged_schema:
        case=protocol['cases'][0];row=next(r for r in values if r.get('case')==case['id'] and r.get('arm')=='plan')
        row['reply']='not JSON';row.update(runner.grade_plan(row['reply'],case))
    calls=[]
    def canonical(value):return sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest() if value is not None else None
    for n,row in enumerate(values,1):
        row['provider_call_id']=str(n);row['request_sha256']=sha256(json.dumps(row['request'],ensure_ascii=False).encode()).hexdigest()
        fmt=row['request'].get('response_format');schema=fmt['json_schema']['schema'] if fmt else None
        calls.append({'id':str(n),'messages':row['request']['messages'],'response':row['reply'],'stream':row['request']['stream'],'analysis':fmt is not None,'finish_reason':'stop','outcome':'completed','grammar_enabled':fmt is not None,'response_format':fmt,'request_body_sha256':row['request_sha256'],'response_format_sha256':canonical(fmt),'response_schema_sha256':canonical(schema)})
    trace=tmp_path/'provider-trace.jsonl';trace.write_text('\n'.join(json.dumps(v) for v in calls)+'\n')
    prior=tmp_path/'probe.json';prior.write_text(json.dumps({'freeze_sha256':'freeze','model_id':runner.MODELS[0],'completed':True,'engineering_passed':True,'cleanup_passed':True,'provider_exit':0,'native_trace_sha256':runner.digest(trace),'requests':values}))
    if forged_schema:
        with pytest.raises(ValueError,match='actual schema evidence incomplete'):runner.prior_gate(prior,'freeze',runner.digest(prior))
    else:runner.prior_gate(prior,'freeze',runner.digest(prior))


def test_truncated_warmup_stops_before_second_call_and_cleans_owned_provider(tmp_path,monkeypatch,protocol):
    from types import SimpleNamespace
    args=SimpleNamespace(model=runner.MODELS[0],output=tmp_path/'run',freeze=tmp_path/'unused.json',expected_freeze_sha256='frozen',provider_python=Path(sys.executable))
    registry=json.loads((ROOT/runner.REGISTRY).read_text());registry_sha=runner.digest(ROOT/runner.REGISTRY)
    source={'sha256':{runner.REGISTRY:registry_sha,'scripts/serve_local_model_eval.py':'provider-sha','src/avatar/gpu_resources.py':'resource-sha'}}
    monkeypatch.setattr(runner,'verify_freeze',lambda *a,**k:source)
    monkeypatch.setattr(runner,'load_registry',lambda *a,**k:(registry,registry_sha,ROOT/runner.REGISTRY))
    monkeypatch.setattr(runner,'validate_provider_identity',lambda *a,**k:None)
    monkeypatch.setattr(runner,'environment',lambda *a:{})
    monkeypatch.setattr(runner,'gpu_processes',lambda:'')
    class OwnedProvider:
        pid=987654321
        def __init__(self,*a,**k):
            self.returncode=None
            metadata={'pid':self.pid,'model_id':args.model,'provider_source_sha256':'provider-sha','resource_selector_sha256':'resource-sha','configuration':{'n_gpu_layers':-1,'n_ctx':8192,'temperature':0,'seed':42,'max_tokens_cap':512,'thinking':False,'concurrent_sequences':1},'chosen_gpu':{'index':0},'url':'fixture'}
            (args.output/'provider-ready.json').write_text(json.dumps(metadata))
        def poll(self):return self.returncode
        def terminate(self):self.returncode=0
        def wait(self,**k):return self.returncode
    monkeypatch.setattr(runner.subprocess,'Popen',OwnedProvider)
    monkeypatch.setattr(runner.subprocess,'check_output',lambda *a,**k:'fixture-head\n')
    calls=[]
    def truncated(url,value):
        calls.append(value);return {'request':value,'reply':'unfinished','finish_reason':'length'}
    monkeypatch.setattr(runner,'request',truncated)
    with pytest.raises(RuntimeError,match='incomplete'):runner.run(args)
    result=json.loads((args.output/'probe.json').read_text())
    assert len(calls)==1 and len(result['requests'])==1
    assert result['provider_exit']==0 and result['cleanup_passed']
    assert not result['completed'] and not result['engineering_passed']
