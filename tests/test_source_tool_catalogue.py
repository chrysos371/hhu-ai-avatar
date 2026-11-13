"""Source/catalogue/clarification boundaries for isolated read-mode; no model."""
from contextlib import closing
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import time

import pytest

from avatar.brain.memory import MemoryStore
from avatar.cancellation import Cancelled, CancellationToken
from avatar.lab.source_tool_catalogue import (
    CatalogueReadSession, ReferenceClarification, STATE, POLICY, CLARIFY,
)

CONTRACT=Path(__file__).resolve().parents[1]/'evals/interaction/cycle-42/source-tool-catalogue-contract.json'
TOOLS=json.loads(CONTRACT.read_text())['declared_tools']
SECRET='目录不应读取的私有事项'


def projection(memory):
    return {name:[dict(row) for row in memory._conn.execute('SELECT * FROM '+name+' ORDER BY id')]
            for name in ('memory_reminders','memory_reminder_deliveries','memory_action_receipts')}


@pytest.fixture
def lab():
    with closing(MemoryStore(':memory:')) as memory:
        session=CatalogueReadSession(memory,'c42-controls')
        memory._conn.execute('INSERT INTO memory_reminders(id,title,due_at,created_at) VALUES (1,?,?,?)',
                             (SECRET,time.time()-60,time.time()-3600))
        memory._conn.commit()
        yield memory,session


@pytest.mark.parametrize('variant,expected',[
    ('full',[STATE,POLICY]),('eligible_bound',[POLICY]),('eligible_complete',[POLICY,CLARIFY])])
def test_current_no_id_policy_question_has_source_based_choices_not_forced_execution(lab,variant,expected):
    memory,session=lab
    session.begin_turn('如果我把这个程序关掉，到时间你还一定能提醒我吗？')
    before,changes=projection(memory),memory._conn.total_changes
    trace=[];memory._conn.set_trace_callback(trace.append)
    cat=session.catalogue(TOOLS,variant)
    cat.require_current(session)
    assert cat.metadata['advertised_names']==expected and cat.bound_reminder_id is None
    assert cat.metadata['semantic_intent_verified'] is False and cat.metadata['business_data_read'] is False
    assert not any('FROM memory_reminders' in sql for sql in trace)
    assert memory._conn.total_changes==changes and projection(memory)==before
    assert SECRET not in repr(cat) and SECRET not in json.dumps(cat.metadata,ensure_ascii=False)


@pytest.mark.parametrize('text,ident',[
    ('提醒编号1现在是什么状态？',1),('编号0001的提醒还能找到吗？',1),
    ('提醒#999是否存在？',999),('提醒编号9223372036854775807是什么状态？',2**63-1)])
@pytest.mark.parametrize('variant',['eligible_bound','eligible_complete'])
def test_current_id_is_bound_in_schema_without_reading_record_existence(lab,text,ident,variant):
    memory,session=lab
    session.begin_turn(text)
    trace=[];memory._conn.set_trace_callback(trace.append)
    cat=session.catalogue(TOOLS,variant)
    assert cat.metadata['advertised_names']==[STATE,POLICY] and cat.bound_reminder_id==ident
    props=cat.tools[0]['function']['parameters']['properties']['reminder_id']
    assert props=={'type':'integer','minimum':1,'maximum':2**63-1,'const':ident}
    assert not any('FROM memory_reminders' in sql for sql in trace)
    result=session.execute(STATE,{'reminder_id':ident})
    assert result.ok and result.data['exists']==(ident==1)
    assert session.publish(result)==result.reply


def test_baseline_preserves_exact_original_two_schemas_and_has_no_const(lab):
    _,session=lab
    session.begin_turn('提醒编号1现在是什么状态？')
    cat=session.catalogue(TOOLS,'full')
    assert cat.tools==TOOLS[:2]
    assert 'const' not in cat.tools[0]['function']['parameters']['properties']['reminder_id']


@pytest.mark.parametrize('text',[
    '提醒编号1和提醒编号2分别是什么状态？','提醒编号1，提醒编号1。',
    '提醒文字是“提醒编号1”。','提醒文字是`提醒编号1`。',
    '提醒编号１是什么状态？','提醒编号1２是什么状态？',
    '提醒编号1.5是什么状态？','提醒编号9223372036854775808是什么状态？'])
def test_unusable_number_basis_never_advertises_state_tool(lab,text):
    _,session=lab
    session.begin_turn(text)
    cat=session.catalogue(TOOLS,'eligible_complete')
    assert STATE not in cat.metadata['advertised_names'] and cat.bound_reminder_id is None
    assert cat.metadata['advertised_names']==[POLICY,CLARIFY]


@pytest.mark.parametrize('text',[
    '不要查询提醒编号1。','帮我改写提醒编号1的台词。',
    '请引用“提醒编号1”，只写一句。','你好，今天聊点轻松的事情。'])
@pytest.mark.parametrize('variant',['eligible_bound','eligible_complete'])
def test_rule_excluded_cases_offer_no_tools_and_do_not_need_a_model(lab,text,variant):
    memory,session=lab
    session.begin_turn(text)
    before,changes=projection(memory),memory._conn.total_changes
    cat=session.catalogue(TOOLS,variant)
    assert cat.tools==[]
    reply=session.no_read_reply(cat)
    assert '这次没有读取' in reply and SECRET not in reply
    assert projection(memory)==before and memory._conn.total_changes==changes


def test_catalogue_schema_and_metadata_accessors_return_independent_values(lab):
    _,session=lab
    session.begin_turn('提醒编号1现在是什么状态？')
    original=deepcopy(TOOLS)
    cat=session.catalogue(TOOLS,'eligible_complete')
    sha=cat.metadata['catalogue_sha256']
    modified=cat.tools
    modified[0]['function']['parameters']['properties']['reminder_id']['const']=12345
    meta=cat.metadata;meta['advertised_names'].append('send_email')
    assert cat.tools[0]['function']['parameters']['properties']['reminder_id']['const']==1
    assert cat.metadata['catalogue_sha256']==sha and TOOLS==original
    cat.require_current(session)


@pytest.mark.parametrize('change',['duplicate','unknown','extra','bad-state-type','bool-minimum','extra-state-key','bad-policy','bad-root'])
def test_untrusted_or_changed_base_registry_cannot_be_silently_used(lab,change):
    _,session=lab;session.begin_turn('提醒编号1现在是什么状态？')
    tools=deepcopy(TOOLS)
    if change=='duplicate':tools[2]=deepcopy(tools[0])
    elif change=='unknown':tools[0]['function']['name']='send_email'
    elif change=='extra':tools[0]['function']['scope']='current_user'
    elif change=='bad-state-type':tools[0]['function']['parameters']['properties']['reminder_id']['type']='string'
    elif change=='bool-minimum':tools[0]['function']['parameters']['properties']['reminder_id']['minimum']=True
    elif change=='extra-state-key':tools[0]['function']['parameters']['properties']['scope']={'type':'string'}
    elif change=='bad-policy':tools[1]['function']['parameters']['properties']={'query':{'type':'string'}}
    else:tools={}
    with pytest.raises(ValueError):session.catalogue(tools,'eligible_complete')


def test_catalogue_cannot_be_replayed_on_another_identical_live_source(lab):
    _,session=lab;session.begin_turn('提醒编号1现在是什么状态？')
    cat=session.catalogue(TOOLS,'eligible_complete')
    with closing(MemoryStore(':memory:')) as other_memory:
        other=CatalogueReadSession(other_memory,'c42-controls')
        other.begin_turn('提醒编号1现在是什么状态？')
        with pytest.raises(Cancelled):cat.require_current(other)


def test_replaced_or_older_catalogue_is_not_issued_current_metadata(lab):
    _,session=lab;session.begin_turn('提醒编号1现在是什么状态？')
    cat=session.catalogue(TOOLS,'eligible_complete')
    with pytest.raises(Cancelled):replace(cat,tools_json='[]').require_current(session)
    session.catalogue(TOOLS,'full')
    with pytest.raises(Cancelled):cat.require_current(session)


@pytest.mark.parametrize('change',['new-turn','text','role','session','revision','delete','new-user'])
def test_catalogue_rechecks_actual_source_after_changes(lab,change):
    memory,session=lab;ident=session.begin_turn('提醒编号1现在是什么状态？')
    cat=session.catalogue(TOOLS,'eligible_complete')
    if change=='new-turn':session.begin_turn('请核对提醒送达条件。')
    elif change=='text':memory._conn.execute('UPDATE memory_messages SET content=? WHERE id=?',('变更文本',ident))
    elif change=='role':memory._conn.execute('UPDATE memory_messages SET role=? WHERE id=?',('assistant',ident))
    elif change=='session':memory._conn.execute('UPDATE memory_messages SET session_id=? WHERE id=?',('other',ident))
    elif change=='revision':memory._conn.execute('UPDATE memory_context_revision SET revision=revision+1')
    elif change=='delete':memory._conn.execute('DELETE FROM memory_messages WHERE id=?',(ident,))
    else:memory.add_message('user','另一来源','other')
    memory._conn.commit()
    with pytest.raises(Cancelled):cat.require_current(session)


@pytest.mark.parametrize('entry',['我来扮演一个虚构角色。','我准备扮演林间守卫。'])
def test_fiction_and_unknown_source_never_get_a_catalogue(lab,entry):
    _,session=lab;session.begin_turn(entry);session.begin_turn('提醒编号1现在是什么状态？')
    with pytest.raises(Cancelled):session.catalogue(TOOLS,'full')


def test_mixed_exit_is_not_authorized_by_new_turn_permission(lab):
    _,session=lab;session.begin_turn('我来扮演一个虚构角色。')
    session.begin_turn('提醒编号1的状况告诉我，回到现实。')
    assert session.speaker.read('controls')['real_actions_for_new_turn'] is True
    with pytest.raises(Cancelled):session.catalogue(TOOLS,'eligible_complete')
    session.begin_turn('提醒编号1现在是什么状态？')
    assert session.catalogue(TOOLS,'eligible_complete').bound_reminder_id==1


def test_catalogue_requires_released_caller_snapshot_for_model_planning(lab):
    memory,session=lab;session.begin_turn('提醒编号1现在是什么状态？')
    cat=session.catalogue(TOOLS,'eligible_complete')
    memory._conn.execute('BEGIN')
    with pytest.raises(Cancelled,match='released'):session.catalogue(TOOLS,'full')
    with pytest.raises(Cancelled,match='released'):cat.require_current(session)
    assert memory._conn.in_transaction
    memory._conn.rollback()
    cat.require_current(session)


def test_clarification_is_not_a_successful_read_or_error_and_has_no_business_sql(lab):
    memory,session=lab;session.begin_turn('我之前设的那条提醒现在是什么状态？')
    before,changes=projection(memory),memory._conn.total_changes
    trace=[];memory._conn.set_trace_callback(trace.append)
    result=session.execute(CLARIFY,{})
    assert isinstance(result,ReferenceClarification)
    assert result.kind=='reference_clarification' and not result.business_data_read and not result.business_mutations
    assert not hasattr(result,'ok') and not hasattr(result,'error')
    assert '当前没有唯一编号' in session.publish(result)
    assert not any('FROM memory_reminders' in sql for sql in trace)
    assert projection(memory)==before and memory._conn.total_changes==changes


@pytest.mark.parametrize('text,args',[
    ('提醒编号1现在是什么状态？',{}),
    ('不要查看提醒状态。',{}),
    ('普通聊天。',{}),
    ('我之前设的那条提醒现在是什么状态？',{'source_message_id':1}),
    ('我之前设的那条提醒现在是什么状态？',{'reminder_id':12345}),
    ('我之前设的那条提醒现在是什么状态？',[]),
])
def test_clarification_action_checks_its_own_arguments_and_preconditions(lab,text,args):
    _,session=lab;session.begin_turn(text)
    result=session.execute(CLARIFY,args)
    assert not isinstance(result,ReferenceClarification) and not result.ok and result.data is None
    assert SECRET not in session.publish(result)


def test_clarification_publication_inherits_caller_transaction_and_latest_result_guard(lab):
    memory,session=lab;session.begin_turn('我之前设的那条提醒现在是什么状态？')
    memory._conn.execute('BEGIN')
    result=session.execute(CLARIFY,{})
    assert memory._conn.in_transaction
    with pytest.raises(Cancelled,match='released'):session.publish(result)
    memory._conn.rollback()
    assert session.publish(result)==result.reply
    with pytest.raises(Cancelled):session.publish(replace(result,reply='假装已读取'))
    session.execute(POLICY,{})
    with pytest.raises(Cancelled):session.publish(result)


def test_clarification_and_catalogue_cancel_after_public_forget(lab):
    memory,session=lab
    fact=memory.remember('公开遗忘版本控制事实')
    session.begin_turn('我之前设的那条提醒现在是什么状态？')
    cat=session.catalogue(TOOLS,'eligible_complete');result=session.execute(CLARIFY,{})
    memory.forget(fact)
    with pytest.raises(Cancelled):cat.require_current(session)
    with pytest.raises(Cancelled):session.publish(result)


def test_cancellation_after_catalogue_never_permits_model_use_or_clarification(lab):
    memory,_=lab;token=CancellationToken()
    session=CatalogueReadSession(memory,'c42-cancel',checkpoint=token.checkpoint)
    session.begin_turn('我之前设的那条提醒现在是什么状态？')
    cat=session.catalogue(TOOLS,'eligible_complete');token.cancel()
    with pytest.raises(Cancelled):cat.require_current(session)
    with pytest.raises(Cancelled):session.execute(CLARIFY,{})


def test_schema_hint_does_not_replace_execution_source_validation(lab):
    memory,session=lab;session.begin_turn('提醒编号1现在是什么状态？')
    cat=session.catalogue(TOOLS,'eligible_complete')
    assert cat.tools[0]['function']['parameters']['properties']['reminder_id']['const']==1
    before,changes=projection(memory),memory._conn.total_changes
    trace=[];memory._conn.set_trace_callback(trace.append)
    result=session.execute(STATE,{'reminder_id':12345})
    assert not result.ok and result.error['code']=='unbound_reminder_id' and result.data is None
    assert not any('FROM memory_reminders r' in sql for sql in trace)
    assert SECRET not in session.publish(result)
    assert projection(memory)==before and memory._conn.total_changes==changes
