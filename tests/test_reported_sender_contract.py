"""A supplied actor source must not become assistant execution or unknown by default."""
from contextlib import closing

import pytest

from avatar.brain.memory import MemoryStore
from avatar.main import Avatar
from avatar.brain.communication_sources import reported_sender
from avatar.cancellation import Cancelled
from test_capability_prompt_lab import Recorder


@pytest.mark.parametrize('source,question,actor', [
    ('我刚才自己给同学发了短信，他还没回。', '是谁发的短信？', 'user'),
    ('室友说他已经把通知发给班长了，我没有发送。', '到底是谁发送的？', '室友'),
])
def test_sender_is_read_from_verified_user_report_without_new_model_or_execution(source, question, actor):
    engine = Recorder('收到你的说明。')
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        original = bot.respond(source)['conversation']['user_message_id']
        counts = len(engine.native), len(engine.analysis)
        engine.reply = '是我发送的，我已经替你处理了。'
        result = bot.respond(question)
        assert result['generation_mode'] == 'rules_reported_sender'
        assert (len(engine.native), len(engine.analysis)) == counts
        evidence = result['reported_communication']
        assert evidence['reported_actor'] == actor and evidence['source_message_ids'] == [original]
        assert not evidence['external_state_verified'] and not evidence['human_acknowledgement_verified']
        assert '按你' in result['reply'] and not result['action_receipts']['items']
        assistant = result['conversation']['assistant_message_id']
        assert memory._conn.execute("SELECT 1 FROM memory_response_context WHERE message_id=? AND source_type='message' AND source_id=?", (assistant, original)).fetchone()


def test_missing_sender_source_is_explicitly_bounded_unknown_and_not_a_model_guess():
    engine = Recorder('是我发的。')
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        result = bot.respond('是谁发的短信？')
        assert result['generation_mode'] == 'rules_reported_sender'
        assert not engine.native and not engine.analysis
        assert result['reported_communication']['reported_actor'] is None
        assert result['reported_communication']['source_message_ids'] == []
        assert '当前' in result['reply'] and '不足' in result['reply']


@pytest.mark.parametrize('source,actor', [
    ('我的室友已经发了邮件。', '室友'),
    ('我和同学已经一起发了短信。', '你和同学'),
    ('我刚才发了短信，你觉得他什么时候回复？', 'user'),
    ('我明天会发短信。', None),
    ('我听说室友已经发了短信。', '室友'),
    ('室友说班长已经发了短信。', '班长'),
])
def test_reported_subject_and_modality_do_not_become_assistant_or_wrong_self(source, actor):
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=Recorder('收到。'), capability_contract_enabled=True)
        bot.respond(source)
        result = bot.respond('是谁发的短信？')
        assert result['reported_communication']['reported_actor'] == actor
        assert not result['reported_communication']['external_state_verified']


def test_later_negative_source_does_not_resurrect_old_positive_sender():
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=Recorder('收到。'), capability_contract_enabled=True)
        bot.respond('我已经发了短信。')
        correction = bot.respond('不是我发的。')['conversation']['user_message_id']
        result = bot.respond('是谁发的短信？')
        assert result['reported_communication']['reported_actor'] is None
        assert result['reported_communication']['source_message_ids'] == [correction]


def test_direct_source_reader_does_not_write_or_commit_callers_transaction():
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=Recorder('收到。'), capability_contract_enabled=True)
        bot.respond('我刚才已经发了短信。')
        bot.respond('是谁发的短信？')
        args = dict(text='是谁发的短信？', session_id=bot.session_id,
            source_message_id=bot._current_message_id, revision=memory.context_revision, scope=bot.speaker_scope)
        before = memory._conn.total_changes
        reported_sender(memory, **args)
        assert not memory._conn.in_transaction and memory._conn.total_changes == before
        memory._conn.execute('BEGIN')
        try:
            reported_sender(memory, **args)
            assert memory._conn.in_transaction and memory._conn.total_changes == before
        finally:
            memory._conn.rollback()
        old = bot.speaker_scope.context_source_ids[0]
        memory._conn.execute("UPDATE memory_messages SET content='[redacted]' WHERE id=?", (old,))
        memory._conn.commit()
        with pytest.raises(Cancelled):
            reported_sender(memory, **args)
