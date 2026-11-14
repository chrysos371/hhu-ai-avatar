"""Dedicated queries through the actual SDK orchestration, with real SQLite."""
from contextlib import closing

import pytest

from avatar.brain.memory import MemoryStore
from avatar.cancellation import Cancelled, CancellationToken
from avatar.main import Avatar
from test_capability_prompt_lab import Recorder
from test_reminder_query_flow import SECRET, seed, projection


@pytest.mark.parametrize('configured', [False, True])
@pytest.mark.parametrize('text,route', [
    ('提醒编号1现在是什么状态？', 'read_state'),
    ('提醒编号1能通过短信送给我吗？', 'read_policy'),
    ('这条提醒取消了吗？', 'clarify_reference'),
    ('提醒编号1的状态和程序运行条件是什么？', 'clarify_intent'),
    ('请取消提醒编号1', 'no_read'),
    ('提醒我明天九点喝水', 'no_read'),
    ('请帮我发短信提醒', 'no_read'),
])
def test_sdk_mode_no_model_no_tool_or_due_writes_and_single_source(text, route, configured):
    model = Recorder('不应调用模型'); model.available = configured
    with closing(MemoryStore(':memory:')) as memory:
        seed(memory)
        bot = Avatar(memory=memory, llm=model)
        before = projection(memory)
        result = bot.respond(text, mode='reminder_query')
        assert result['reminder_query']['route'] == route
        assert result['generation_mode'] == result['analysis_mode'] == 'rules_reminder_query'
        assert not model.analysis and not model.native
        assert not result['due_reminders'] and not result['tool_calls']
        assert projection(memory) == before
        rows = memory._conn.execute('SELECT role,content FROM memory_messages').fetchall()
        assert [tuple(r) for r in rows] == [('user', text), ('assistant', result['reply'])]
        assert not memory.get_user_profile()


@pytest.mark.parametrize('options', [
    {'mode': None}, {'mode': True}, {'mode': 'unknown'},
    {'mode': 'reminder_query', 'use_web': True},
])
def test_invalid_options_leave_no_source(options):
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=Recorder('unused'))
        with pytest.raises(ValueError): bot.respond('提醒编号1状态？', **options)
        assert memory._conn.execute('SELECT count(*) FROM memory_messages').fetchone()[0] == 0


def test_untracked_sdk_history_requires_separate_durable_exit_then_query():
    model = Recorder('普通对话。'); model.available = False
    with closing(MemoryStore(':memory:')) as memory:
        seed(memory, due=False)
        bot = Avatar(memory=memory, llm=model)
        bot.respond('我来扮演一个虚构角色。')
        denied = bot.respond('提醒编号1状态？', mode='reminder_query')
        assert denied['generation_mode'] == 'rules_speaker_scope'
        assert 'reminder_query' not in denied and SECRET not in denied['reply']
        mixed = bot.respond('回到现实。查询提醒编号1', mode='reminder_query')
        assert 'reminder_query' not in mixed and SECRET not in mixed['reply']
        bot.respond('回到现实')
        result = bot.respond('提醒编号1状态？', mode='reminder_query')
        assert result['reminder_query']['route'] == 'read_state' and SECRET in result['reply']


def test_later_chat_explicitly_inherits_saved_query_reply_and_normal_due_behavior():
    model = Recorder('普通回复。')
    with closing(MemoryStore(':memory:')) as memory:
        seed(memory)
        bot = Avatar(memory=memory, llm=model)
        result = bot.respond('提醒编号1状态？', mode='reminder_query')
        assert not model.native and not model.analysis
        ordinary = bot.respond('接着聊聊')
        assert len(model.native) == len(model.analysis) == 1
        assert result['reply'] in str(model.native[0]) and SECRET in str(model.analysis[0])
        assert len(ordinary['due_reminders']) == 1


@pytest.mark.parametrize('interrupt', ['cancel', 'new_source', 'revision'])
def test_actual_sdk_interruption_after_read_does_not_commit_or_publish_reply(monkeypatch, interrupt):
    from avatar.brain.reminder_query_mode import ReminderQueryReader
    original = ReminderQueryReader.resolve
    with closing(MemoryStore(':memory:')) as memory:
        seed(memory)
        token = CancellationToken(); pieces = []
        def wrapped(reader):
            value = original(reader)
            if interrupt == 'cancel': token.cancel()
            elif interrupt == 'new_source': memory.add_message('user', 'another', 'other')
            else:
                with memory.transaction():
                    memory._conn.execute('UPDATE memory_context_revision SET revision=revision+1 WHERE id=1')
            return value
        monkeypatch.setattr(ReminderQueryReader, 'resolve', wrapped)
        bot = Avatar(memory=memory, llm=Recorder('unused'))
        with pytest.raises(Cancelled):
            bot.respond('提醒编号1状态？', mode='reminder_query', cancel=token, on_delta=pieces.append)
        assert not pieces
        assert memory._conn.execute("SELECT count(*) FROM memory_messages WHERE role='assistant'").fetchone()[0] == 0
        assert not projection(memory)['memory_reminder_deliveries']
