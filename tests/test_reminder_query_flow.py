"""Explicit reads through Avatar and actual HTTP; no automatic reminder writes."""
from contextlib import closing
import json
import time
import urllib.request

import pytest

from avatar.brain.memory import MemoryStore
from avatar.brain.reminders import ReminderStore
from avatar.cancellation import CancellationToken, Cancelled
from avatar.main import Avatar
from test_capability_prompt_lab import Recorder
from test_web_api_v1 import api_v1

SECRET = '私密查询控制标题'


def seed(memory, *, due=True):
    store = ReminderStore(memory)
    now = time.time()
    memory._conn.execute('INSERT INTO memory_reminders(title,due_at,created_at) VALUES (?,?,?)',
                         (SECRET,now-60 if due else now+3600,now-120))
    memory._conn.commit()
    return store


def projection(memory):
    return {name:[dict(r) for r in memory._conn.execute('SELECT * FROM '+name+' ORDER BY id')]
            for name in ['memory_reminders','memory_reminder_deliveries','memory_action_receipts']}


@pytest.mark.parametrize('text', ['查询提醒编号1','查看提醒送达条件','查询提醒编号0','查询提醒编号1，再取消提醒1'])
@pytest.mark.parametrize('configured', [False, True])
def test_explicit_controls_use_no_model_or_web_and_do_not_claim_even_overdue(text, configured):
    model = Recorder('不应由模型答复此控制')
    model.available = configured
    class NoWeb:
        def run(self,*args,**kwargs): raise AssertionError('read query must not dispatch web tools')
    with closing(MemoryStore(':memory:')) as memory:
        seed(memory)
        bot = Avatar(memory=memory,llm=model,web_agent=NoWeb())
        before = projection(memory)
        result = bot.respond(text,use_web=True,cancel=CancellationToken())
        assert result['generation_mode'] == result['analysis_mode'] == 'rules_reminder_query'
        assert result['reminder_query']['source_message_id'] == result['conversation']['user_message_id']
        assert not result['due_reminders'] and not result['tool_calls'] and not result['action_receipts']['items']
        assert projection(memory)==before and not model.analysis and not model.native
        assert memory._conn.execute('SELECT content FROM memory_messages WHERE id=?',
            (result['conversation']['assistant_message_id'],)).fetchone()[0] == result['reply']
        assert len(memory._conn.execute('SELECT * FROM memory_messages').fetchall()) == 2


def test_normal_turn_after_read_still_claims_and_persists_due_event():
    model = Recorder('普通聊天回复。')
    with closing(MemoryStore(':memory:')) as memory:
        seed(memory)
        bot = Avatar(memory=memory,llm=model)
        bot.respond('查询提醒编号1')
        assert not projection(memory)['memory_reminder_deliveries']
        result = bot.respond('今天聊点什么？')
        assert 'reminder_query' not in result and len(result['due_reminders']) == 1
        assert SECRET in result['reply'] and len(projection(memory)['memory_reminder_deliveries']) == 1
        assert result['action_receipts']['items'][0]['action'] == 'reminder.claimed_due'
        assert len(model.analysis)==len(model.native)==1


@pytest.mark.parametrize('entry', ['我来扮演一个虚构角色。','我准备扮演林间守卫。'])
def test_role_or_unverified_query_does_not_read_or_leak_real_reminder(entry):
    model = Recorder('不应读取秘密')
    with closing(MemoryStore(':memory:')) as memory:
        seed(memory)
        bot=Avatar(memory=memory,llm=model)
        bot.respond(entry)
        before=projection(memory)
        result=bot.respond('查询提醒编号1')
        assert result['generation_mode']=='rules_speaker_scope' and result['speaker_tool_blocked']
        assert 'reminder_query' not in result and SECRET not in result['reply']
        assert projection(memory)==before and not model.analysis and not model.native


@pytest.mark.parametrize('text', ['“查询提醒编号1”','写一句“查询提醒编号1”的台词。','回到现实，查询提醒编号1'])
def test_noncommands_and_mixed_scope_do_not_gain_query_authority(text):
    model=Recorder('普通文本，不含真人提醒。')
    with closing(MemoryStore(':memory:')) as memory:
        seed(memory,due=False)
        bot=Avatar(memory=memory,llm=model)
        result=bot.respond(text)
        assert 'reminder_query' not in result and SECRET not in result['reply']
        assert result['generation_mode']!='rules_reminder_query'


def test_existing_explicit_web_list_alias_is_preserved():
    class LegacyWeb:
        def __init__(self):self.calls=[]
        def run(self,text,llm,**kwargs):
            self.calls.append(text)
            return {'reply':'原列表工具答复。','sources':[],'tool_calls':[]}
    web=LegacyWeb()
    with closing(MemoryStore(':memory:')) as memory:
        seed(memory,due=False)
        bot=Avatar(memory=memory,llm=Recorder('unused'),web_agent=web)
        result=bot.respond('查看提醒',use_web=True)
        assert web.calls==['查看提醒'] and result['reply']=='原列表工具答复。'
        assert 'reminder_query' not in result


def test_old_writing_delivery_contract_does_not_review_readonly_control():
    model=Recorder('不应生成')
    with closing(MemoryStore(':memory:')) as memory:
        seed(memory)
        bot=Avatar(memory=memory,llm=model,task_contract_enabled=True,delivery_check_enabled=True)
        bot.tasks.update('帮我写一句给同学的回复，只要正文：明天见。')
        assert bot.tasks.current is not None
        result=bot.respond('查询提醒编号1')
        assert result['generation_mode']=='rules_reminder_query'
        assert not result['delivery_check']['remaining_issues'] and not result['delivery_check']['repair_attempted']
        assert not model.analysis and not model.native


@pytest.mark.parametrize('interrupt', ['cancel','forget'])
def test_privacy_change_after_read_snapshot_prevents_visible_or_stored_answer(tmp_path,monkeypatch,interrupt):
    from avatar.brain import reminder_queries
    path=str(tmp_path/'query-privacy.db')
    with closing(MemoryStore(path)) as memory,closing(MemoryStore(path)) as writer:
        seed(memory)
        root=memory.add_message('user','受控私密来源。','old')
        fact=memory.remember('受控私密来源',source_message_id=root)
        bot=Avatar(memory=memory,llm=Recorder('must not run'))
        token=CancellationToken(); pieces=[]; original=reminder_queries.resolve_query
        def wrapped(*args,**kwargs):
            value=original(*args,**kwargs)
            assert not memory._conn.in_transaction
            if interrupt=='cancel': token.cancel()
            else: writer.forget(fact)
            return value
        monkeypatch.setattr(reminder_queries,'resolve_query',wrapped)
        with pytest.raises(Cancelled):
            bot.respond('查询提醒编号1',cancel=token,on_delta=pieces.append)
        assert not pieces and memory._conn.execute("SELECT count(*) FROM memory_messages WHERE role='assistant'").fetchone()[0]==0
        assert not projection(memory)['memory_reminder_deliveries']


def test_actual_http_sse_query_result_and_SQL_remain_readonly(api_v1,monkeypatch):
    import avatar.main as module
    request,server=api_v1
    model=Recorder('unused')
    class RealQueryAvatar(Avatar):
        def __init__(self,*args,**kwargs):
            kwargs['llm']=model
            super().__init__(*args,**kwargs)
    monkeypatch.setattr(module,'Avatar',RealQueryAvatar)
    with closing(MemoryStore(server.db_path)) as memory:
        seed(memory)
        before=projection(memory)
    ident='reminder-query-http-control-0001'
    assert request('/api/v1/turns',{'request_id':ident,'text':'查询提醒编号1'})[0]==202
    req=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/v1/turns/{ident}/events',headers={'X-Avatar-Token':server.token})
    with urllib.request.urlopen(req,timeout=10) as response:
        raw=response.read().decode()
    results=[json.loads(line[6:]) for block in raw.split('\n\n') if 'event: result\n' in block
             for line in block.splitlines() if line.startswith('data: ')]
    assert len(results)==1
    result=results[0]
    assert result['generation_mode']=='rules_reminder_query' and SECRET in result['reply']
    assert not result['tool_calls'] and not result['action_receipts']['items']
    assert result['reminder_query']['state']['id']==1 and not result['reminder_query']['state']['service_claim_recorded']
    assert not model.analysis and not model.native
    with closing(MemoryStore(server.db_path)) as memory:
        assert projection(memory)==before
        row=memory._conn.execute('SELECT content FROM memory_messages WHERE id=?',
                                (result['conversation']['assistant_message_id'],)).fetchone()
        assert row[0]==result['reply']
