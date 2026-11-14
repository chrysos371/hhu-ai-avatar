"""Actual committed-source and no-write controls for the dedicated reader."""
from contextlib import closing
from dataclasses import replace
import time

import pytest

from avatar.brain.memory import MemoryStore
from avatar.brain.reminders import ReminderStore
from avatar.brain.reminder_queries import QuerySource
from avatar.brain.reminder_query_mode import ReminderQueryReader
from avatar.brain.speaker_context import SpeakerContextStore
from avatar.cancellation import Cancelled, CancellationToken


def prepare(memory, text):
    reminders = ReminderStore(memory)
    now = time.time()
    with memory.transaction():
        memory._conn.execute('INSERT INTO memory_reminders(title,due_at,created_at) VALUES (?,?,?)',
                             ('专用查询标题', now-60, now-3600))
        ident = memory.add_message('user', text, 'session')
        scope = SpeakerContextStore(memory).observe(text, memory.context_revision, ident)
    return reminders, QuerySource(ident, 'session', memory.context_revision, scope.scope, scope.allows_actions)


def projection(memory):
    return [list(memory._conn.execute('SELECT * FROM '+name)) for name in (
        'memory_reminders', 'memory_reminder_deliveries', 'memory_action_receipts')]


@pytest.mark.parametrize('text,route,selects', [
    ('提醒编号1现在是什么状态？', 'read_state', 1),
    ('提醒编号1能通过短信送给我吗？', 'read_policy', 0),
    ('这条提醒取消了吗？', 'clarify_reference', 0),
    ('提醒编号1是什么状态，程序关掉还能提醒吗？', 'clarify_intent', 0),
    ('请取消提醒编号1', 'no_read', 0),
    ('你好', 'no_read', 0),
])
def test_real_sqlite_typed_routes_only_state_reads_business_and_no_mutations(text, route, selects):
    with closing(MemoryStore(':memory:')) as memory:
        store, source = prepare(memory, text)
        before = projection(memory); changes = memory._conn.total_changes
        sql = []; memory._conn.set_trace_callback(sql.append)
        reader = ReminderQueryReader(store, text, source)
        result = reader.resolve(); reader.ensure_current()
        memory._conn.set_trace_callback(None)
        assert result.metadata['route'] == route and result.metadata['model_calls'] == 0
        assert result.metadata['source_message_id'] == source.source_message_id
        assert len([s for s in sql if 'FROM memory_reminders' in s]) == selects
        assert not result.metadata['business_mutations'] and not memory._conn.in_transaction
        assert memory._conn.total_changes == changes and projection(memory) == before
        if selects:
            assert result.metadata['state']['title'] == '专用查询标题'
            assert not result.metadata['state']['service_claim_recorded']


@pytest.mark.parametrize('mutation', ['role', 'content', 'session', 'revision', 'new_user', 'speaker'])
def test_changed_source_refused_before_read_and_before_publication(mutation):
    with closing(MemoryStore(':memory:')) as memory:
        text = '提醒编号1状态？'; store, source = prepare(memory, text)
        reader = ReminderQueryReader(store, text, source)
        reader.resolve()  # A legitimate prior observation cannot be undone.
        with memory.transaction():
            if mutation in ('role', 'content', 'session'):
                field = {'role': 'role', 'content': 'content', 'session': 'session_id'}[mutation]
                memory._conn.execute('UPDATE memory_messages SET '+field+'=? WHERE id=?', ('wrong', source.source_message_id))
            elif mutation == 'revision':
                memory._conn.execute('UPDATE memory_context_revision SET revision=revision+1 WHERE id=1')
            elif mutation == 'new_user':
                memory.add_message('user', 'new', 'another')
            else:
                memory._conn.execute("UPDATE memory_web_speaker_state SET scope='unverified' WHERE id=1")
        with pytest.raises(Cancelled): reader.ensure_current()
        with pytest.raises(Cancelled): reader.resolve()


def test_mixed_exit_cannot_be_authorized_by_forged_caller_scope():
    with closing(MemoryStore(':memory:')) as memory:
        text = '回到现实。查询提醒编号1'
        store, source = prepare(memory, text)
        assert not source.turn_tools_allowed
        with pytest.raises(Cancelled):
            ReminderQueryReader(store, text, replace(source, scope='current_user', turn_tools_allowed=True))


def test_caller_transaction_rejected_without_committing_and_cancelled_read_releases_snapshot():
    with closing(MemoryStore(':memory:')) as memory:
        text = '提醒编号1状态？'; store, source = prepare(memory, text)
        memory._conn.execute('BEGIN')
        memory._conn.execute("UPDATE memory_reminders SET title='pending'")
        with pytest.raises(Cancelled): ReminderQueryReader(store, text, source)
        assert memory._conn.in_transaction
        memory._conn.rollback()
        token = CancellationToken()
        reader = ReminderQueryReader(store, text, source, checkpoint=token.checkpoint)
        token.cancel()
        with pytest.raises(Cancelled): reader.resolve()
        assert not memory._conn.in_transaction
        assert memory._conn.execute('SELECT title FROM memory_reminders').fetchone()[0] == '专用查询标题'
