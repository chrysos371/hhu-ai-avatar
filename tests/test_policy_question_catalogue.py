"""Actual source/SQLite policy-topic controls; no model or network."""
from contextlib import closing
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import time

import pytest

from avatar.brain.memory import MemoryStore
from avatar.cancellation import Cancelled, CancellationToken
from avatar.lab.source_tool_catalogue import CatalogueReadSession, STATE, POLICY, CLARIFY, ReferenceClarification
from avatar.lab.policy_question_catalogue import (
    PolicyQuestionReadSession, PolicyQuestionCatalogue, policy_question_evidence,
    RUNTIME_CUE_PATTERN, RECORD_REFERENCE_PATTERN, RECORD_STATE_PATTERN,
)

ROOT=Path(__file__).resolve().parents[1]
CONTRACT=json.loads((ROOT/'evals/interaction/cycle-43/policy-question-evidence-contract.json').read_text())
TOOLS=json.loads((ROOT/'evals/interaction/cycle-43/policy-question-trial-protocol.json').read_text())['tools']
SECRET='不应被目录读取的私有事项'


def business(memory):
    return {name:[dict(r) for r in memory._conn.execute('SELECT * FROM '+name+' ORDER BY id')]
        for name in ('memory_reminders','memory_reminder_deliveries','memory_action_receipts')}


@pytest.fixture
def lab():
    with closing(MemoryStore(':memory:')) as memory:
        session=PolicyQuestionReadSession(memory,'c43-controls')
        memory._conn.execute('INSERT INTO memory_reminders(id,title,due_at,created_at) VALUES(1,?,?,?)',
            (SECRET,time.time()-60,time.time()-3600))
        memory._conn.commit()
        yield memory,session


def test_exact_patterns_were_preregistered_before_implementation():
    assert CONTRACT['patterns']=={'runtime_cue':RUNTIME_CUE_PATTERN,
        'record_reference':RECORD_REFERENCE_PATTERN,'record_state':RECORD_STATE_PATTERN}


@pytest.mark.parametrize('text',[
    '如果我把这个程序关掉，到时间你还一定能提醒我吗？',
    '网页不在线的时候，本机提醒能通过短信送给我吗？',
    '提醒服务停止运行时，还能发送通知吗？',
    '我不打开网页，还能在浏览器里收到本机提醒吗？',
    '提醒编号1能通过短信送给我吗？',
    '电脑进入休眠时，本机提醒还能自动通知吗？',
    '程序处于关闭状态时，本机提醒还会通知吗？',
    '这条提醒如果碰到程序退出，还能通过短信发给我吗？',
])
def test_policy_questions_have_actual_visible_evidence_without_reading_rows(lab,text):
    memory,session=lab;session.begin_turn(text)
    before,changes=business(memory),memory._conn.total_changes
    trace=[];memory._conn.set_trace_callback(trace.append)
    cat=session.catalogue(TOOLS)
    evidence=cat.policy_evidence
    assert evidence.allowed and POLICY in cat.metadata['advertised_names']
    assert cat.metadata['semantic_intent_verified'] is False
    for start,end,word in evidence.runtime_spans:assert text[start:end]==word
    result=session.execute(POLICY,{})
    assert result.ok and result.data['requires_running_server'] and '无法自动投递' in session.publish(result)
    assert SECRET not in repr(cat) and not any('FROM memory_reminders' in sql for sql in trace)
    assert memory._conn.total_changes==changes and business(memory)==before


@pytest.mark.parametrize('text,code',[
    ('我之前设的那条提醒现在是什么状态？','record_state_not_policy'),
    ('我想查那条提醒，但没提供具体编号，请别猜它是哪一条。','runtime_policy_basis_missing'),
    ('那条提醒后来取消了吗？我没有选具体记录。','record_state_not_policy'),
    ('那条提醒的状态是不是已送达？','record_state_not_policy'),
    ('那条提醒的状态和网页运行有关吗？','record_state_not_policy'),
    ('请看提醒编号1的状态。','record_state_not_policy'),
])
def test_unavailable_policy_is_independently_denied_before_any_business_read(lab,text,code):
    memory,session=lab;session.begin_turn(text)
    trace=[];memory._conn.set_trace_callback(trace.append)
    cat=session.catalogue(TOOLS)
    assert not cat.policy_evidence.allowed and cat.policy_evidence.error==code
    assert POLICY not in cat.metadata['advertised_names']
    changes=memory._conn.total_changes
    result=session.execute(POLICY,{})  # Deliberate direct bypass of advertised schemas.
    assert not result.ok and result.data is None and result.error['code']==code
    assert '不能' in session.publish(result) and SECRET not in result.reply
    assert memory._conn.total_changes==changes and not any('FROM memory_reminders' in sql for sql in trace)


@pytest.mark.parametrize('text',[
    '我想知道这条提醒，“程序退出”只是引用。',
    '我想知道这条提醒，`网页`只在代码中。',
    '我想知道这条提醒，```短信',
    '我想知道这条提醒，~~~电话',
    '我想知道这条提醒，“程序「网页」短信”只是字面内容。',
])
def test_quoted_and_code_runtime_cues_cannot_supply_evidence(text):
    evidence=policy_question_evidence(text)
    assert not evidence.allowed and not evidence.runtime_spans


def test_c42_baseline_and_state_query_remain_unchanged(lab):
    memory,session=lab;session.begin_turn('我想知道编号1的提醒目前是什么状态，你能查一下吗？')
    cat=session.catalogue(TOOLS)
    assert cat.metadata['advertised_names']==[STATE]
    assert cat.tools[0]['function']['parameters']['properties']['reminder_id']['const']==1
    read=session.execute(STATE,{'reminder_id':1});assert read.ok and SECRET in session.publish(read)
    baseline=CatalogueReadSession(memory,'c43-baseline');baseline.begin_turn('我想知道那条提醒现在的状态。')
    assert baseline.catalogue(TOOLS,'eligible_complete').metadata['advertised_names']==[POLICY,CLARIFY]
    assert baseline.execute(POLICY,{}).ok


def test_missing_reference_clarifies_without_business_success_or_SQL(lab):
    memory,session=lab;session.begin_turn('我之前设的那条提醒现在是什么状态？')
    cat=session.catalogue(TOOLS);assert cat.metadata['advertised_names']==[CLARIFY]
    before,changes=business(memory),memory._conn.total_changes
    trace=[];memory._conn.set_trace_callback(trace.append)
    clarification=session.execute(CLARIFY,{})
    assert isinstance(clarification,ReferenceClarification) and not hasattr(clarification,'ok')
    assert not clarification.business_data_read and '编号' in session.publish(clarification)
    assert not any('FROM memory_reminders' in sql for sql in trace)
    assert memory._conn.total_changes==changes and business(memory)==before


def test_catalogue_metadata_and_schema_copies_cannot_change_authoritative_evidence(lab):
    _,session=lab;session.begin_turn('那条提醒的状态和网页运行有关吗？')
    cat=session.catalogue(TOOLS);assert isinstance(cat,PolicyQuestionCatalogue)
    meta=cat.metadata;sha=meta['catalogue_sha256']
    meta['policy_question_evidence']['error']=None;meta['advertised_names'].append(POLICY)
    cat.tools.append(TOOLS[1])
    assert cat.metadata['catalogue_sha256']==sha and not cat.policy_evidence.allowed
    canonical=lambda x:json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    current=cat.metadata;digest=current.pop('catalogue_sha256')
    assert hashlib.sha256(canonical(current).encode()).hexdigest()==digest
    assert session.execute(POLICY,{}).error['code']=='record_state_not_policy'
    forged=replace(cat,policy_evidence=replace(cat.policy_evidence,error=None))
    with pytest.raises(Cancelled):forged.require_current(session)


@pytest.mark.parametrize('change',['new-turn','redact','forget','cross-session','role','cancel'])
def test_actual_source_changes_cannot_be_repaired_by_policy_topic_metadata(lab,change):
    memory,session=lab;token=CancellationToken();session._checkpoint=token.checkpoint
    ident=session.begin_turn('程序退出后，本机提醒还能通知吗？');cat=session.catalogue(TOOLS)
    result=session.execute(POLICY,{})
    if change=='new-turn':session.begin_turn('那条提醒现在是什么状态？')
    elif change=='forget':memory.forget(memory.remember('临时事实'))
    elif change=='cancel':token.cancel()
    else:
        column,value={'redact':('content','[redacted]'),'cross-session':('session_id','other'),
            'role':('role','assistant')}[change]
        memory._conn.execute('UPDATE memory_messages SET '+column+'=? WHERE id=?',(value,ident));memory._conn.commit()
    with pytest.raises(Cancelled):cat.require_current(session)
    with pytest.raises(Cancelled):session.publish(result)


@pytest.mark.parametrize('text',[
    '不要查询提醒服务运行条件。','帮我改写提醒服务退出的台词。',
    '你好，程序可以运行了吗？',
])
def test_old_domain_and_exclusion_gates_take_precedence(lab,text):
    _,session=lab;session.begin_turn(text);cat=session.catalogue(TOOLS)
    assert cat.tools==[]
    result=session.execute(POLICY,{})
    assert not result.ok and result.error['code'] in ('read_intent_excluded','local_reminder_domain_not_explicit')


@pytest.mark.parametrize('arguments,code',[(None,'invalid_arguments'),([], 'invalid_arguments'),
    ({'authorized':True},'unexpected_arguments'),({'policy_source_error':None},'unexpected_arguments')])
def test_model_arguments_cannot_override_policy_authority(lab,arguments,code):
    _,session=lab;session.begin_turn('程序退出后，本机提醒还能通知吗？')
    result=session.execute(POLICY,arguments)
    assert not result.ok and result.error['code']==code


def test_caller_transaction_is_not_committed_by_planning_execution_or_publication(lab):
    memory,session=lab;session.begin_turn('程序退出后，本机提醒还能通知吗？')
    memory._conn.execute('BEGIN')
    memory._conn.execute("INSERT INTO memory_messages(role,content,session_id,created_at) VALUES('assistant','pending','x',?)",(time.time(),))
    with pytest.raises(Cancelled):session.catalogue(TOOLS)
    assert memory._conn.in_transaction
    read=session.execute(POLICY,{})
    assert read.ok and memory._conn.in_transaction
    with pytest.raises(Cancelled):session.publish(read)
    memory._conn.rollback()
    assert memory._conn.execute("SELECT COUNT(*) FROM memory_messages WHERE content='pending'").fetchone()[0]==0


def test_startup_rejects_active_caller_transaction_before_schema_commit():
    with closing(MemoryStore(':memory:')) as memory:
        memory._conn.execute('BEGIN')
        memory._conn.execute("INSERT INTO memory_messages(role,content,session_id,created_at) VALUES('assistant','pending','x',?)",(time.time(),))
        with pytest.raises(Cancelled):PolicyQuestionReadSession(memory,'pending')
        assert memory._conn.in_transaction
        memory._conn.rollback()
        assert memory._conn.execute("SELECT COUNT(*) FROM memory_messages WHERE content='pending'").fetchone()[0]==0


def test_older_or_cross_instance_policy_catalogue_is_rejected(lab):
    memory,session=lab;session.begin_turn('程序退出后，本机提醒还能通知吗？')
    old=session.catalogue(TOOLS);current=session.catalogue(TOOLS)
    with pytest.raises(Cancelled):old.require_current(session)
    other=PolicyQuestionReadSession(memory,'other')
    with pytest.raises(Cancelled):current.require_current(other)


def test_source_reentry_during_final_checkpoint_cannot_publish_old_policy(lab):
    _,session=lab;session.begin_turn('程序退出后，本机提醒还能通知吗？')
    called=[0]
    def checkpoint():
        called[0]+=1
        if called[0]==2:
            session._checkpoint=lambda:None
            session.begin_turn('我之前设的那条提醒现在是什么状态？')
    session._checkpoint=checkpoint
    with pytest.raises(Cancelled):session.execute(POLICY,{})
    assert session._last_result is None
