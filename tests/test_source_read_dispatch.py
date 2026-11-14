"""Actual source/SQLite/direct-operation controls; no network or model."""
from contextlib import closing
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import time

import pytest

from avatar.brain.memory import MemoryStore
from avatar.cancellation import Cancelled, CancellationToken
from avatar.lab.source_tool_catalogue import STATE,POLICY,CLARIFY,ReferenceClarification
from avatar.lab.source_read_dispatch import (
    SourceReadDispatchSession, QueryIntentClarification, NoReadOutcome,
    derive_read_target, QUERY_REQUEST_PATTERN, WRITING_REQUEST_PATTERN,
    MUTATION_REQUEST_PATTERN, EXTERNAL_ACTION_REQUEST_PATTERN,
)

ROOT=Path(__file__).resolve().parents[1]
CONTRACT=json.loads((ROOT/'evals/interaction/cycle-44/source-read-dispatch-contract.json').read_text())
SECRET='不应被计划读取的私有事项'


def business(memory):
    return {name:[dict(r) for r in memory._conn.execute('SELECT * FROM '+name+' ORDER BY id')]
        for name in ('memory_reminders','memory_reminder_deliveries','memory_action_receipts')}


@pytest.fixture
def lab():
    with closing(MemoryStore(':memory:')) as memory:
        session=SourceReadDispatchSession(memory,'c44-controls')
        memory._conn.execute('INSERT INTO memory_reminders(id,title,due_at,created_at) VALUES(1,?,?,?)',
            (SECRET,time.time()-60,time.time()-3600));memory._conn.commit()
        yield memory,session


def test_exact_frame_patterns_were_registered_before_implementation():
    assert CONTRACT['patterns']=={'query_request':QUERY_REQUEST_PATTERN,'writing_request':WRITING_REQUEST_PATTERN,
        'mutation_request':MUTATION_REQUEST_PATTERN,'external_action_request':EXTERNAL_ACTION_REQUEST_PATTERN}


@pytest.mark.parametrize('text',[
    '提醒编号1现在是什么状态？','请核对提醒编号999是否还存在。',
    '我想看编号1的提醒记录。','提醒编号1现在取消了吗？',
    '已经取消的提醒编号1是否还存在？',
    '取消的提醒编号1是否还存在？',
])
def test_record_queries_use_unique_current_id_and_actual_read_without_model(lab,text):
    memory,session=lab;session.begin_turn(text)
    before,changes=business(memory),memory._conn.total_changes
    trace=[];memory._conn.set_trace_callback(trace.append)
    plan=session.plan()
    assert plan.target.route=='read_state' and not plan.metadata['model_required']
    assert not plan.metadata['business_data_read'] and SECRET not in repr(plan)
    assert not any('FROM memory_reminders' in sql for sql in trace)
    read=session.dispatch(plan);reply=session.publish(read)
    assert read.ok and read.data['id'] in (1,999) and reply==read.reply
    assert sum('FROM memory_reminders r' in sql for sql in trace)==1
    assert business(memory)==before and memory._conn.total_changes==changes


@pytest.mark.parametrize('text',[
    '提醒编号1能通过短信送给我吗？','程序退出后，本机提醒还能通知吗？',
    '程序处于关闭状态时，本机提醒还能通知吗？',
    '网页不在线的时候，本机提醒能通过短信送给我吗？',
])
def test_runtime_target_takes_precedence_over_a_merely_mentioned_id(lab,text):
    memory,session=lab;session.begin_turn(text);trace=[];memory._conn.set_trace_callback(trace.append)
    plan=session.plan();assert plan.target.route=='read_policy'
    result=session.dispatch(plan)
    assert result.ok and result.data['external_delivery_channels']==[]
    assert '程序运行' in session.publish(result) and not any('FROM memory_reminders' in sql for sql in trace)
    # Direct operation call cannot bypass the target using a legitimate ID.
    denied=session.execute(STATE,{'reminder_id':1})
    assert not denied.ok and denied.error['code']=='read_target_not_requested'
    assert not any('FROM memory_reminders' in sql for sql in trace)


@pytest.mark.parametrize('text',[
    '我之前设的那条提醒现在是什么状态？','那条提醒的状态是不是已送达？',
    '那条提醒后来取消了吗？','我想查那条提醒的状态，“网页关闭”是标题里的字。',
    '提醒编号1和提醒编号2现在是什么状态？',
])
def test_reference_clarification_is_distinct_and_does_not_read_business(lab,text):
    memory,session=lab;session.begin_turn(text)
    trace=[];memory._conn.set_trace_callback(trace.append)
    plan=session.plan();assert plan.target.route=='clarify_reference'
    result=session.dispatch(plan);assert isinstance(result,ReferenceClarification)
    assert '编号' in session.publish(result) and not hasattr(result,'ok') and not result.business_data_read
    assert not any('FROM memory_reminders' in sql for sql in trace)
    assert not session.execute(POLICY,{}).ok


@pytest.mark.parametrize('text,reason',[
    ('请核对提醒编号1的状态，也说说网页关闭时还能收到提醒吗？','mixed_read_targets'),
    ('那条提醒的状态与网页运行有关吗？','mixed_read_targets'),
    ('提醒这个功能到底是什么？','query_goal_unspecified'),
    ('关于提醒，我应该查询哪种信息？','query_goal_unspecified'),
])
def test_intent_clarification_does_not_falsely_ask_for_missing_id(lab,text,reason):
    memory,session=lab;session.begin_turn(text)
    trace=[];memory._conn.set_trace_callback(trace.append)
    plan=session.plan();assert plan.target.route=='clarify_intent' and plan.target.reason==reason
    result=session.dispatch(plan);assert isinstance(result,QueryIntentClarification)
    assert result.reason==reason and not result.business_data_read and not hasattr(result,'ok')
    assert '未读取' in session.publish(result)
    assert not any('FROM memory_reminders' in sql for sql in trace)
    for tool,args in [(STATE,{'reminder_id':1}),(POLICY,{}),(CLARIFY,{})]:
        assert session.execute(tool,args).error['code']=='read_target_not_requested'


@pytest.mark.parametrize('text',[
    '我的提醒程序已经退出了。','我还保存着提醒编号1。',
    '请帮我取消提醒编号1，好吗？','帮我把提醒编号1取消掉。',
    '请现在取消提醒编号1。','现在取消提醒编号1。',
    '现在把提醒编号1取消。',
    '帮我写一段代码查询提醒编号1。','生成一段检查提醒编号1的代码。',
    '请帮我给老师发一封邮件提醒他。','替我通过短信提醒老师。',
    '不要查询提醒编号1。','你好，今天聊点轻松的事情。',
])
def test_nonqueries_and_writes_are_legitimate_no_read_controls_without_mutations(lab,text):
    memory,session=lab;session.begin_turn(text)
    before,changes=business(memory),memory._conn.total_changes
    trace=[];memory._conn.set_trace_callback(trace.append)
    plan=session.plan();assert plan.target.route=='no_read'
    result=session.dispatch(plan);assert isinstance(result,NoReadOutcome)
    assert not result.business_data_read and not result.business_mutations and not hasattr(result,'ok')
    assert '不执行写入或外发' in session.publish(result)
    assert not session.execute(STATE,{'reminder_id':1}).ok
    assert not any('FROM memory_reminders' in sql for sql in trace)
    assert business(memory)==before and memory._conn.total_changes==changes


def test_private_fields_and_source_bindings_cannot_be_overridden_by_plan_views(lab):
    _,session=lab;session.begin_turn('提醒编号1现在是什么状态？')
    plan=session.plan();before=plan.metadata['plan_sha256']
    meta=plan.metadata;meta['arguments']['reminder_id']=999;meta['evidence']['bound_reminder_id']=999
    args=plan.target.arguments;args['reminder_id']=999
    assert plan.target.arguments=={'reminder_id':1} and plan.metadata['plan_sha256']==before
    value=plan.metadata;digest=value.pop('plan_sha256')
    canonical=lambda x:json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    assert hashlib.sha256(canonical(value).encode()).hexdigest()==digest
    forged=replace(plan,target=replace(plan.target,arguments_json='{"reminder_id":999}'))
    with pytest.raises(Cancelled):session.dispatch(forged)


def test_old_cross_instance_and_new_source_plans_are_not_executable(lab):
    memory,session=lab;session.begin_turn('提醒编号1现在是什么状态？')
    old=session.plan();plan=session.plan()
    with pytest.raises(Cancelled):session.dispatch(old)
    other=SourceReadDispatchSession(memory,'other')
    with pytest.raises(Cancelled):other.dispatch(plan)
    result=session.dispatch(plan);session.begin_turn('程序退出后，本机提醒还能通知吗？')
    with pytest.raises(Cancelled):session.dispatch(plan)
    with pytest.raises(Cancelled):session.publish(result)


@pytest.mark.parametrize('change',['redact','forget','cross-session','role','cancel'])
def test_source_permission_changes_refuse_both_plan_and_publication(lab,change):
    memory,session=lab;token=CancellationToken();session._checkpoint=token.checkpoint
    ident=session.begin_turn('提醒编号1现在是什么状态？');plan=session.plan();result=session.dispatch(plan)
    if change=='forget':memory.forget(memory.remember('临时版本事实'))
    elif change=='cancel':token.cancel()
    else:
        column,value={'redact':('content','[redacted]'),'cross-session':('session_id','elsewhere'),
            'role':('role','assistant')}[change]
        memory._conn.execute('UPDATE memory_messages SET '+column+'=? WHERE id=?',(value,ident));memory._conn.commit()
    with pytest.raises(Cancelled):session.dispatch(plan)
    with pytest.raises(Cancelled):session.publish(result)


@pytest.mark.parametrize('arguments',[
    {'reminder_id':999},{'reminder_id':True},{'reminder_id':1,'authorized':True},None,
])
def test_matching_operation_does_not_override_old_parameter_authority(lab,arguments):
    memory,session=lab;session.begin_turn('提醒编号1现在是什么状态？')
    trace=[];memory._conn.set_trace_callback(trace.append)
    result=session.execute(STATE,arguments)
    assert not result.ok and result.error['code']!='read_target_not_requested'
    assert not any('FROM memory_reminders r' in sql for sql in trace)


def test_pending_caller_transaction_is_never_committed(lab):
    memory,session=lab;session.begin_turn('提醒编号1现在是什么状态？');plan=session.plan()
    memory._conn.execute('BEGIN')
    memory._conn.execute("INSERT INTO memory_messages(role,content,session_id,created_at) VALUES('assistant','pending','x',?)",(time.time(),))
    with pytest.raises(Cancelled):session.plan()
    with pytest.raises(Cancelled):session.dispatch(plan)
    read=session.execute(STATE,{'reminder_id':1});assert read.ok and memory._conn.in_transaction
    with pytest.raises(Cancelled):session.publish(read)
    memory._conn.rollback()
    assert memory._conn.execute("SELECT COUNT(*) FROM memory_messages WHERE content='pending'").fetchone()[0]==0


def test_startup_rejects_pending_transaction_before_schema_commit():
    with closing(MemoryStore(':memory:')) as memory:
        memory._conn.execute('BEGIN')
        memory._conn.execute("INSERT INTO memory_messages(role,content,session_id,created_at) VALUES('assistant','pending','x',?)",(time.time(),))
        with pytest.raises(Cancelled):SourceReadDispatchSession(memory,'pending')
        assert memory._conn.in_transaction
        memory._conn.rollback()
        assert memory._conn.execute("SELECT COUNT(*) FROM memory_messages WHERE content='pending'").fetchone()[0]==0


@pytest.mark.parametrize('stage',['before-execute','during-execute'])
def test_reentry_checkpoint_cannot_read_an_operation_for_a_new_source(lab,stage):
    memory,session=lab;session.begin_turn('提醒编号1现在是什么状态？')
    called=[0];trace=[];memory._conn.set_trace_callback(trace.append)
    def checkpoint():
        called[0]+=1
        if called[0]==(1 if stage=='before-execute' else 2):
            session._checkpoint=lambda:None
            session.begin_turn('提醒编号1能通过短信送给我吗？')
    session._checkpoint=checkpoint
    with pytest.raises(Cancelled):session.execute(STATE,{'reminder_id':1})
    assert not any('FROM memory_reminders r' in sql for sql in trace)


@pytest.mark.parametrize('text',['',None,'提醒'*1001])
def test_pure_target_derivation_refuses_unbounded_or_invalid_source(text):
    with pytest.raises(ValueError):derive_read_target(text)
