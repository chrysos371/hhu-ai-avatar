"""Boundary tests for standalone research renderer; no production activation."""
import importlib.util
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('native_evidence_plan',ROOT/'scripts/native_evidence_plan.py')
module=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(module)


def context():
    return {'namespace':'isolated-A','revision':4,'request_id':'req-3','capabilities':{'sms':False,'email':False,'phone':False,'local_reminder':True},'atoms':[
        {'id':'a7','kind':'draft','actor':'user','text':'我已经把材料发给老师了。','namespace':'isolated-A','revision':4},
        {'id':'a2','kind':'action_report','actor':'user','text':'我刚才自己给同学发了短信。','namespace':'isolated-A','revision':4},
        {'id':'r8','kind':'reminder_receipt','actor':'assistant','text':'去图书馆','namespace':'isolated-A','revision':4,'request_id':'req-3','committed':True}]}


def plan(operation,reference='none',actor='assistant'):return {'operation':operation,'reference':reference,'actor':actor}


def test_literal_sent_draft_preserves_exact_text_without_adding_action_claim():
    assert module.render(plan('copy_draft','a7','user'),context())=={'channel':'draft','text':'我已经把材料发给老师了。','source':'a7'}


def test_actor_answer_uses_supplied_report_without_treating_draft_as_action():
    assert module.render(plan('answer_actor','a2','user'),context())['text']=='发送者是用户。'
    with pytest.raises(ValueError):module.render(plan('answer_actor','a7','user'),context())


@pytest.mark.parametrize('change',[{'namespace':'other'},{'revision':3},{'request_id':'req-2'},{'committed':False}])
def test_receipt_rejects_other_namespace_revision_request_or_uncommitted(change):
    ctx=context();ctx['atoms'][2].update(change)
    with pytest.raises(ValueError):module.render(plan('report_receipt','r8'),ctx)


def test_real_fixture_receipt_reports_only_committed_state_not_display_delivery():
    text=module.render(plan('report_receipt','r8'),context())['text']
    assert '已提交' in text and '已送达' not in text and '已读' not in text


@pytest.mark.parametrize('value',[plan('answer_actor','a2','contact'),plan('copy_draft','missing','user'),plan('report_receipt','a7'),{'operation':'copy_draft','reference':'a7','actor':'user','text':'我发出去了'},plan('unknown')])
def test_invalid_plan_or_reference_rejected_without_gold(value):
    with pytest.raises(ValueError):module.render(value,context())


def test_valid_but_wrong_draft_is_not_filtered_using_hidden_gold():
    ctx=context();ctx['atoms'].append(dict(ctx['atoms'][0],id='a9',text='不同的草稿。'))
    assert module.render(plan('copy_draft','a9','user'),ctx)['text']=='不同的草稿。'


def test_external_boundary_requires_actual_empty_external_capabilities():
    assert '无法' in module.render(plan('capability_boundary'),context())['text']
    ctx=context();ctx['capabilities']['sms']=True
    with pytest.raises(ValueError):module.render(plan('capability_boundary'),ctx)


def test_payload_excludes_gold_and_both_arms_share_context():
    case={'id':'x','question':'谁发的？','context':context(),'gold':{'secret':'do not send'}}
    plain=module.payload(case,'plain');typed=module.payload(case,'plan')
    assert plain['messages']==typed['messages'] and 'secret' not in str(typed)
    assert 'response_format' not in plain and typed['response_format']['json_schema']['strict'] is True
    assert len(typed['response_format']['json_schema']['schema']['properties']['reference']['enum'])>1


def test_duplicate_json_key_and_nonfinite_value_rejected():
    with pytest.raises(ValueError):module.decode('{"actor":"user","actor":"assistant"}')
    with pytest.raises(ValueError):module.decode('{"x":NaN}')
