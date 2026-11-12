"""Three-arm source, protocol and exact wire schedule authorization controls."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import probe_native_evidence_plans_v2 as runner


@pytest.fixture
def protocol():return json.loads((ROOT/runner.PROTOCOL).read_text())


def values(protocol):
    out=[]
    for index,stream in enumerate(protocol['warmups']):
        out.append({'role':'warmup','warmup_index':index,'request':{'model':runner.MODELS[0],'messages':[{'role':'user','content':'请回答：你好。'}],'stream':stream,'temperature':0,'max_tokens':16},'reply':'你好','finish_reason':'stop'})
    for case,order in zip(protocol['cases'],protocol['arm_orders']):
        for arm in order:
            row={'role':'source_atom_three_arm_diagnostic','case':case['id'],'arm':arm,'request':runner.payload(case,arm,runner.MODELS[0]),'reply':json.dumps(case['gold'],ensure_ascii=False) if arm!='natural' else 'fixture natural','finish_reason':'stop'}
            if arm!='natural':row.update(runner.grade_plan(row['reply'],case))
            out.append(row)
    return out


def test_all38_requests_account_for_three_arms_and_unconstrained_plans(protocol):
    rows=values(protocol);assert len(rows)==38
    runner.validate_rows(rows,protocol,runner.MODELS[0])
    assert sum('response_format' in row['request'] for row in rows)==12
    free=[r for r in rows if r.get('arm')=='plan_free'];assert len(free)==12 and all(r['plan_exact'] for r in free)


@pytest.mark.parametrize('key,value',[('scope','old-two-arm'),('backend','cpu'),('same_messages_between_plan_arms',False),('same_question_context_between_all_arms',False),('natural_contains_plan_instructions',True),('diagnostic_requests_per_model',24),('source_protocol','other'),('source_protocol_sha256','0'*64),('production_activation_authorized',True),('prospective_execution_authorized',True),('gold_sent_to_model',True)])
def test_declared_contract_cannot_be_silently_ignored(protocol,key,value):
    protocol[key]=value
    with pytest.raises(ValueError):runner.validate_protocol(protocol)


def test_known_case_or_gold_cannot_drift_from_preregistered_c27_source(protocol):
    protocol['cases'][0]['gold']['operation']='insufficient_evidence'
    with pytest.raises(ValueError):runner.validate_protocol(protocol)


@pytest.mark.parametrize('change',['drop_free_arm','swap_labels','leak_gold','grade_override','unconstrained_became_schema'])
def test_raw_request_schedule_and_free_plan_grading_not_replaceable_by_flags(protocol,change):
    rows=values(protocol);row=next(r for r in rows if r.get('arm')=='plan_free')
    if change=='drop_free_arm':rows.remove(row)
    elif change=='swap_labels':row['arm']='natural'
    elif change=='leak_gold':row['request']['messages'][-1]['content']+=' GOLD'
    elif change=='grade_override':row['plan_exact']=False
    else:row['request']['response_format']=runner.payload(protocol['cases'][0],'plan_schema')['response_format']
    with pytest.raises(ValueError):runner.validate_rows(rows,protocol,runner.MODELS[0])


def test_unconstrained_plan_malformed_json_is_semantic_format_failure_not_engineering_abort(protocol):
    rows=values(protocol);case=protocol['cases'][0];row=next(r for r in rows if r.get('arm')=='plan_free' and r.get('case')==case['id'])
    row['reply']='not a plan';row.update(runner.grade_plan(row['reply'],case))
    runner.validate_rows(rows,protocol,runner.MODELS[0])
    assert not row['declared_schema_valid'] and not row['render_passed']


def test_actual_os_wrong_descriptor_sha_fails_before_any_output_or_model(tmp_path):
    path=tmp_path/'freeze.json';path.write_text('{invalid');output=tmp_path/'no-output'
    call=[sys.executable,str(ROOT/'scripts/probe_native_evidence_plans_v2.py'),'--model',runner.MODELS[0],'--output',str(output),'--freeze',str(path),'--expected-freeze-sha256','0'*64,'--provider-python',sys.executable]
    result=subprocess.run(call,capture_output=True,text=True,cwd=ROOT)
    assert result.returncode!=0 and 'Freeze descriptor identity changed' in result.stderr and not output.exists()


def test_freeze_includes_python_dependencies_of_existing_regression_suite():
    names=runner.required_paths()
    assert 'scripts/probe_native_evidence_plans.py' in names
    assert 'scripts/probe_native_evidence_plans_v2.py' in names
    assert 'scripts/native_evidence_plan_v2.py' in names
    assert 'tests/test_native_evidence_plan_runner_v2.py' in names


@pytest.mark.parametrize('variant',['complete','free_invalid','schema_invalid'])
def test38_call_prior_evidence_requires_actual_constrained_validity_not_free_plan_success(tmp_path,protocol,variant):
    from hashlib import sha256
    rows=values(protocol)
    if variant!='complete':
        target='plan_free' if variant=='free_invalid' else 'plan_schema'
        row=next(r for r in rows if r.get('arm')==target);case=next(c for c in protocol['cases'] if c['id']==row['case'])
        row['reply']='invalid JSON';row.update(runner.grade_plan(row['reply'],case))
    calls=[]
    def canonical(value):return sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest() if value is not None else None
    for n,row in enumerate(rows,1):
        row['provider_call_id']=str(n);row['request_sha256']=sha256(json.dumps(row['request'],ensure_ascii=False).encode()).hexdigest()
        fmt=row['request'].get('response_format');schema=fmt['json_schema']['schema'] if fmt else None
        calls.append({'id':str(n),'messages':row['request']['messages'],'response':row['reply'],'stream':row['request']['stream'],'analysis':fmt is not None,'finish_reason':'stop','outcome':'completed','grammar_enabled':fmt is not None,'response_format':fmt,'request_body_sha256':row['request_sha256'],'response_format_sha256':canonical(fmt),'response_schema_sha256':canonical(schema)})
    trace=tmp_path/'provider-trace.jsonl';trace.write_text('\n'.join(json.dumps(v) for v in calls)+'\n')
    prior=tmp_path/'probe.json';prior.write_text(json.dumps({'freeze_sha256':'freeze','model_id':runner.MODELS[0],'completed':True,'engineering_passed':True,'cleanup_passed':True,'provider_exit':0,'native_trace_sha256':runner.digest(trace),'requests':rows}))
    if variant=='schema_invalid':
        with pytest.raises(ValueError,match='actual schema evidence incomplete'):runner.prior_gate(prior,'freeze',runner.digest(prior))
    else:runner.prior_gate(prior,'freeze',runner.digest(prior))
