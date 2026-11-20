"""Real SQLite source/receipt tests, without trusting generated claims."""
from contextlib import closing
import dataclasses
import json

import pytest

from avatar.brain.capabilities import checked_tool_inventory, snapshot
from avatar.brain.memory import MemoryStore
from avatar.cancellation import Cancelled
from avatar.main import Avatar


@pytest.fixture
def bot():
    class Unconfigured:
        available = False
    with closing(MemoryStore(':memory:')) as memory:
        value = Avatar(memory=memory, llm=Unconfigured())
        value.respond('聊聊海边。')
        yield value


def read(bot, **overrides):
    args = dict(session_id=bot.session_id, source_message_id=bot._current_message_id,
        user_text='聊聊海边。', revision=bot.memory.context_revision, scope=bot.speaker_scope,
        known_source_ids={bot._current_message_id})
    args.update(overrides)
    return snapshot(bot.memory, **args)


def test_bounded_runtime_facts_are_immutable_and_do_not_invent_delivery(bot):
    value = read(bot)
    data = value.data()
    assert not data['text_generation_executes_actions'] and not data['semantic_verifier']
    assert data['external_delivery'] == {'sms': False, 'email': False, 'phone': False}
    assert data['local_execution']['items'] == [] and not data['local_execution']['complete_history']
    assert not data['local_execution']['human_acknowledgement_verified']
    assert '聊聊海边' not in json.dumps(data, ensure_ascii=False)
    with pytest.raises(dataclasses.FrozenInstanceError):
        value.revision = 2
    data['source']['message_id'] = -1
    assert value.data()['source']['message_id'] == bot._current_message_id
    assert checked_tool_inventory() == ('get_weather', 'list_reminders', 'read_webpage', 'search_documents', 'web_search')


def test_snapshot_preserves_outer_transaction_and_has_no_sql_writes(bot):
    conn = bot.memory._conn
    before = conn.total_changes
    assert not conn.in_transaction
    read(bot)
    assert not conn.in_transaction and conn.total_changes == before
    conn.execute('BEGIN')
    try:
        read(bot)
        assert conn.in_transaction and conn.total_changes == before
    finally:
        conn.rollback()


@pytest.mark.parametrize('field,value', [('role', 'assistant'), ('content', '[redacted]'),
    ('session_id', 'other-session'), ('content', 'different current text')])
def test_changed_current_source_is_rejected(bot, field, value):
    bot.memory._conn.execute('UPDATE memory_messages SET '+field+'=? WHERE id=?', (value, bot._current_message_id))
    bot.memory._conn.commit()
    with pytest.raises(Cancelled):
        read(bot)


@pytest.mark.parametrize('ident', [None, False, True, 0, -1, 2**63, '1'])
def test_unusable_current_source_identity_is_rejected(bot, ident):
    with pytest.raises(Cancelled):
        read(bot, source_message_id=ident)


def test_stale_revision_and_mutable_scope_cannot_reauthorize_snapshot(bot):
    with pytest.raises(Cancelled):
        read(bot, revision=bot.memory.context_revision+1)
    bot.speaker_scope.revision = -1
    with pytest.raises(Cancelled):
        read(bot)


def test_real_local_receipt_requires_existing_reply_source_and_is_not_current_state(bot):
    created = bot.respond('提醒我明天下午3点去海边')
    assert created['reminder']
    origin = bot._current_message_id
    bot.respond('聊聊海边。')
    current = bot._current_message_id
    hidden = read(bot).data()['local_execution']
    assert not hidden['items'] and hidden['complete_history'] is False
    included = read(bot, known_source_ids={origin, current}).data()['local_execution']
    assert len(included['items']) == 1 and included['items'][0]['action'] == 'reminder.created'
    assert included['items'][0]['source_message_id'] == origin
    assert not included['current_reminder_state_verified'] and not included['external_delivery_verified']
    assert not included['human_acknowledgement_verified']


@pytest.mark.parametrize('sources', [set(), {True}, {1, 2**63}, [1]])
def test_missing_or_future_lineage_cannot_authorize_receipt_reads(bot, sources):
    with pytest.raises(Cancelled):
        read(bot, known_source_ids=sources)
