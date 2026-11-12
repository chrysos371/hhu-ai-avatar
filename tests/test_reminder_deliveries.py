"""Durable client acknowledgement contracts; no human perception is inferred."""
from contextlib import closing
import sqlite3
import pytest
from avatar.brain.memory import MemoryStore
from avatar.brain.reminders import ReminderStore

NOW = 1794445000.0


def seed(store, offset=-60):
    row = store.create('提醒我明天下午3点队列实验', now=NOW)
    with store.memory.transaction():
        store.conn.execute('UPDATE memory_reminders SET due_at=? WHERE id=?', (NOW+offset, row['id']))
    return row['id']


def test_stable_replay_across_connections_and_restart_preserves_claim_contract(tmp_path):
    path = str(tmp_path/'queue.db')
    with closing(MemoryStore(path)) as memory:
        store = ReminderStore(memory); rid = seed(store)
        first = store.claim_due(now=NOW)
        assert [r['id'] for r in first] == [rid]
        pending = store.pending_deliveries(now=NOW)
        assert len(pending) == 1 and pending[0]['id'] == rid
        event = pending[0]['delivery_id']
        assert store.claim_due(now=NOW+1) == []
    with closing(MemoryStore(path)) as a, closing(MemoryStore(path)) as b:
        assert ReminderStore(a).pending_deliveries(now=NOW+1)[0]['delivery_id'] == event
        assert ReminderStore(b).pending_deliveries(now=NOW+2)[0]['delivery_id'] == event
        assert ReminderStore(b).claim_due(now=NOW+2) == []
        assert a._conn.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'


def test_enqueue_failure_rolls_back_claim_in_same_transaction(tmp_path):
    with closing(MemoryStore(str(tmp_path/'queue.db'))) as memory:
        store = ReminderStore(memory); seed(store)
        memory._conn.execute("CREATE TRIGGER reject_delivery BEFORE INSERT ON memory_reminder_deliveries BEGIN SELECT RAISE(ABORT,'fixture failure'); END")
        with pytest.raises(sqlite3.IntegrityError, match='fixture failure'):
            store.claim_due(now=NOW)
        assert store.list()[0]['notified_at'] is None
        assert not memory._conn.in_transaction
        memory._conn.execute('DROP TRIGGER reject_delivery')
        assert len(store.pending_deliveries(now=NOW)) == 1


def test_explicit_ack_idempotent_and_does_not_duplicate_content(tmp_path):
    with closing(MemoryStore(str(tmp_path/'queue.db'))) as memory:
        store = ReminderStore(memory); seed(store)
        event = store.pending_deliveries(now=NOW)[0]['delivery_id']
        ack = store.acknowledge_delivery(event, expected_revision=0, now=NOW+1)
        assert ack['acknowledged_at'] == NOW+1
        assert store.pending_deliveries(now=NOW+2) == []
        assert store.acknowledge_delivery(event, expected_revision=0, now=NOW+3) == ack
        columns = [r['name'] for r in memory._conn.execute('PRAGMA table_info(memory_reminder_deliveries)')]
        assert set(columns) == {'id','reminder_id','created_at','acknowledged_at'}
        assert not memory._conn.execute('SELECT * FROM memory_action_receipts').fetchall()


@pytest.mark.parametrize('status', ['cancelled','completed'])
def test_status_change_filters_pending_and_rejects_unseen_ack(tmp_path, status):
    with closing(MemoryStore(str(tmp_path/'queue.db'))) as memory:
        store = ReminderStore(memory); rid = seed(store)
        event = store.pending_deliveries(now=NOW)[0]['delivery_id']
        store.set_status(rid, status)
        assert store.pending_deliveries(now=NOW+1) == []
        with pytest.raises(ValueError, match='delivery_not_pending'):
            store.acknowledge_delivery(event, expected_revision=0, now=NOW+1)
        assert memory._conn.execute('SELECT acknowledged_at FROM memory_reminder_deliveries').fetchone()[0] is None


def test_delete_removes_event_and_cannot_ack(tmp_path):
    with closing(MemoryStore(str(tmp_path/'queue.db'))) as memory:
        store = ReminderStore(memory); rid = seed(store)
        event = store.pending_deliveries(now=NOW)[0]['delivery_id']
        store.delete(rid)
        assert store.pending_deliveries(now=NOW+1) == []
        assert memory._conn.execute('SELECT * FROM memory_reminder_deliveries').fetchall() == []
        with pytest.raises(ValueError, match='delivery_not_pending'):
            store.acknowledge_delivery(event, expected_revision=0, now=NOW+1)


@pytest.mark.parametrize('offset,expected', [(1,0),(-86401,0),(-86400,1),(0,1)])
def test_current_24h_window_is_preserved(tmp_path, offset, expected):
    with closing(MemoryStore(str(tmp_path/'queue.db'))) as memory:
        store = ReminderStore(memory); seed(store, offset)
        assert len(store.pending_deliveries(now=NOW)) == expected
        if expected:
            event = memory._conn.execute('SELECT id FROM memory_reminder_deliveries').fetchone()[0]
            assert store.pending_deliveries(now=NOW+86401) == []
            with pytest.raises(ValueError, match='delivery_not_pending'):
                store.acknowledge_delivery(event, expected_revision=0, now=NOW+86401)


def test_legacy_claim_is_not_fabricated_as_pending_or_ack(tmp_path):
    path = str(tmp_path/'queue.db')
    with closing(MemoryStore(path)) as memory:
        store = ReminderStore(memory); seed(store)
        with memory.transaction():
            memory._conn.execute('UPDATE memory_reminders SET notified_at=?', (NOW-1,))
        assert store.pending_deliveries(now=NOW) == []
        assert memory._conn.execute('SELECT * FROM memory_reminder_deliveries').fetchall() == []


def test_privacy_revision_fences_old_ack_but_preserves_legal_reminder(tmp_path):
    with closing(MemoryStore(str(tmp_path/'queue.db'))) as memory:
        store = ReminderStore(memory); seed(store)
        event = store.pending_deliveries(now=NOW)[0]['delivery_id']
        fragment = memory.remember_user('名字','队列隐私实验名')
        memory.forget(fragment)
        with pytest.raises(ValueError, match='delivery_revision_changed'):
            store.acknowledge_delivery(event, expected_revision=0, now=NOW+1)
        assert len(store.pending_deliveries(now=NOW+1)) == 1
        store.acknowledge_delivery(event, expected_revision=memory.context_revision, now=NOW+2)
        assert store.pending_deliveries(now=NOW+3) == []


@pytest.mark.parametrize('bad', [True,0,-1,2**63,1.5,'1',None])
def test_ack_rejects_invalid_ids_without_mutation(tmp_path, bad):
    with closing(MemoryStore(str(tmp_path/'queue.db'))) as memory:
        store = ReminderStore(memory); seed(store)
        store.pending_deliveries(now=NOW)
        with pytest.raises(ValueError, match='invalid_delivery_ack'):
            store.acknowledge_delivery(bad, expected_revision=0, now=NOW+1)
        assert memory._conn.execute('SELECT acknowledged_at FROM memory_reminder_deliveries').fetchone()[0] is None
