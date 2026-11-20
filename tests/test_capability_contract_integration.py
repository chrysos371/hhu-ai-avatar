"""Opt-in release implementation: real orchestration/SQLite, forced model claims."""
from contextlib import closing
import json
import time

import pytest

from avatar.brain.memory import MemoryStore
from avatar.cancellation import CancellationToken, Cancelled
from avatar.main import Avatar
from test_capability_prompt_lab import Recorder


@pytest.mark.parametrize('text', ['帮我发短信给同学。', '你已经发送短信了吗？',
    '请替我发邮件给老师。', '你刚才联系到他了吗？', '你刚才真的发出去了吗？'])
def test_no_cognition_generation_or_tools_can_invent_explicit_external_execution(text):
    engine = Recorder('已帮你发送成功，稍后再帮你联系。')
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        pieces = []
        result = bot.respond(text, cancel=CancellationToken(), on_delta=pieces.append, use_web=True)
        assert not engine.native and not engine.analysis and bot.web_agent is None
        assert result['generation_mode'] == result['analysis_mode'] == 'rules_capability_request'
        assert '没有接入' in result['reply'] and '发送成功' not in result['reply']
        assert not result['tool_calls'] and not result['action_receipts']['items']
        assert memory.get_short_term()[-1]['content'] == result['reply']
        row = memory._conn.execute("SELECT content FROM memory_messages WHERE role='assistant'").fetchone()
        assert row['content'] == result['reply'] and pieces == []
        assert bot._capability_snapshot.source_message_id == result['conversation']['user_message_id']


@pytest.mark.parametrize('text,reply', [
    ('帮我原样写回复：“我已经把材料发给老师了。”', '我已经把材料发给老师了。'),
    ('写一句小说台词：“短信已经发送成功。”', '“短信已经发送成功。”'),
    ('替我回复朋友，原样写出“周六我陪你去游泳”，不要加解释。', '周六我陪你去游泳。'),
    ('请把“我明天陪你去骑车”改得更客气。', '我很愿意明天陪你去骑车。'),
])
def test_known_creative_protective_regressions_keep_stream_final_and_storage(text, reply):
    engine = Recorder(reply)
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        pieces = []
        result = bot.respond(text, cancel=CancellationToken(), on_delta=pieces.append)
        assert result['reply'] == ''.join(pieces) == memory.get_short_term()[-1]['content'] == reply
        assert result['generation_mode'] == 'llm' and len(engine.native) == len(engine.analysis) == 1
        assert '运行时能力/回执数据' in engine.native[0][0]['content']
        assert not result['action_receipts']['items']


def test_local_reminder_with_external_action_title_remains_real_and_true():
    engine = Recorder('普通答复。')
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        result = bot.respond('请提醒我明天下午3点给老师发邮件。')
        assert result['reminder'] and len(bot.reminders.list()) == 1
        assert result['action_receipts']['items'][0]['action'] == 'reminder.created'
        assert '程序运行并轮询' in result['reply'] and bot._capability_snapshot is None


def test_unavailable_execution_does_not_claim_unrelated_due_reminder():
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=Recorder('wrong'), capability_contract_enabled=True)
        reminder = bot.reminders.create('提醒我2099年1月1日上午10点开会')
        memory._conn.execute('UPDATE memory_reminders SET due_at=? WHERE id=?', (time.time()-1, reminder['id']))
        memory._conn.commit()
        result = bot.respond('请替我发送邮件给老师。')
        assert not result['action_receipts']['items']
        assert memory._conn.execute('SELECT COUNT(*) FROM memory_reminder_deliveries').fetchone()[0] == 0


def test_changed_user_source_cannot_dispatch_even_deterministic_capability_reply(monkeypatch):
    from avatar.brain import capabilities
    original = capabilities.snapshot
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=Recorder('wrong'), capability_contract_enabled=True)
        def altered(*args, **kwargs):
            memory._conn.execute('UPDATE memory_messages SET content=? WHERE id=?',
                ('changed', kwargs['source_message_id']))
            memory._conn.commit()
            return original(*args, **kwargs)
        monkeypatch.setattr(capabilities, 'snapshot', altered)
        with pytest.raises(Cancelled):
            bot.respond('请替我发短信给同学。')
        assert not memory._conn.execute("SELECT 1 FROM memory_messages WHERE role='assistant'").fetchone()


def test_query_mode_keeps_existing_read_only_path_and_does_not_use_capability_prompt():
    engine = Recorder('wrong')
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        result = bot.respond('程序关闭后还能提醒吗？', mode='reminder_query')
        assert result['generation_mode'] == 'rules_reminder_query'
        assert bot._capability_snapshot is None and not engine.analysis and not engine.native
