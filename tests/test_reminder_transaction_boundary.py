"""Invalidation before local action transactions must prevent business writes."""
from contextlib import closing
import sqlite3
import threading
import time

import pytest

from avatar.brain.memory import MemoryStore
from avatar.brain.reminders import ReminderStore
from avatar.cancellation import CancellationToken, Cancelled
from avatar.main import Avatar


@pytest.mark.parametrize('operation', ['create', 'set_status', 'claim_due'])
@pytest.mark.parametrize('change', ['normal', 'cancel', 'forget'])
def test_avatar_revalidates_inside_reminder_write(tmp_path, operation, change):
    class Engine:
        available = False
    path = str(tmp_path/'memory.db'); token = CancellationToken()
    bot = Avatar(db_path=path, llm=Engine())
    fragment = bot.memory.remember_user('名字', '事务测试名')
    if operation != 'create':
        seeded = bot.reminders.create('提醒我明天下午3点事务正控')
        if operation == 'claim_due':
            with bot.memory.transaction():
                bot.memory._conn.execute('UPDATE memory_reminders SET due_at=? WHERE id=?',
                                         (time.time()-10, seeded['id']))
    before = bot.reminders.list(); original = getattr(bot.reminders, operation)
    called = []
    def scheduled(*args, **kwargs):
        assert not bot.memory._conn.in_transaction
        if change == 'cancel': token.cancel()
        elif change == 'forget':
            with closing(MemoryStore(path)) as writer: writer.forget(fragment)
        called.append(True)
        return original(*args, **kwargs)
    setattr(bot.reminders, operation, scheduled)
    text = ('提醒我明天下午3点事务正控' if operation == 'create' else
            '取消提醒'+str(seeded['id']) if operation == 'set_status' else '你好')
    try:
        if change == 'normal':
            assert bot.respond(text, cancel=token)['reply']
            assert bot.reminders.list() != before
        else:
            with pytest.raises(Cancelled): bot.respond(text, cancel=token)
            assert bot.reminders.list() == before
            assert bot.memory._conn.execute(
                "SELECT count(*) FROM memory_messages WHERE role='assistant'").fetchone()[0] == 0
        assert called == [True]
    finally: bot.memory.close()


@pytest.mark.parametrize('operation', ['create', 'set_status', 'claim_due'])
@pytest.mark.parametrize('reject', [False, True])
def test_store_checkpoint_holds_writer_lock(tmp_path, operation, reject):
    path = str(tmp_path/'memory.db')
    with closing(MemoryStore(path)) as memory, closing(MemoryStore(path)) as other:
        store = ReminderStore(memory)
        seeded = store.create('提醒我明天下午3点锁正控')
        with memory.transaction():
            memory._conn.execute('UPDATE memory_reminders SET due_at=?', (time.time()-10,))
        before = store.list(); checked = []
        other._conn.execute('PRAGMA busy_timeout=0')
        def checkpoint():
            assert memory._conn.in_transaction
            with pytest.raises(sqlite3.OperationalError, match='locked'):
                other._conn.execute('BEGIN IMMEDIATE')
            checked.append(True)
            if reject: raise Cancelled('transaction fixture rejected')
        def act():
            if operation == 'create': store.create('提醒我明天下午3点锁正控', checkpoint=checkpoint)
            elif operation == 'set_status': store.set_status(seeded['id'], 'cancelled', checkpoint=checkpoint)
            else: store.claim_due(checkpoint=checkpoint)
        if reject:
            with pytest.raises(Cancelled): act()
            assert store.list() == before
        else:
            act(); assert store.list() != before
        assert checked == [True]
        assert not memory._conn.in_transaction


@pytest.mark.parametrize('operation', ['create', 'set_status', 'claim_due'])
@pytest.mark.parametrize('change', ['cancel', 'forget'])
def test_rechecks_after_waiting_for_other_connection_writer(tmp_path, operation, change):
    path = str(tmp_path/'memory.db'); token = CancellationToken()
    entered, proceed, attempting = threading.Event(), threading.Event(), threading.Event()
    result = {}; errors = []
    with closing(MemoryStore(path)) as writer:
        fragment = writer.remember_user('名字', '等待写锁实验名')
        store = ReminderStore(writer)
        seeded = store.create('提醒我明天下午3点等待写锁')
        with writer.transaction():
            writer._conn.execute('UPDATE memory_reminders SET due_at=?', (time.time()-10,))
        before = store.list()
        def run():
            class Engine:
                available = False
            bot = Avatar(db_path=path, llm=Engine())
            original = getattr(bot.reminders, operation)
            def scheduled(*args, **kwargs):
                entered.set()
                assert proceed.wait(5)
                bot.memory._conn.set_trace_callback(
                    lambda sql: attempting.set() if sql == 'BEGIN IMMEDIATE' else None)
                return original(*args, **kwargs)
            setattr(bot.reminders, operation, scheduled)
            text = ('提醒我明天下午3点等待写锁' if operation == 'create' else
                    '取消提醒'+str(seeded['id']) if operation == 'set_status' else '你好')
            try:
                try: result['reply'] = bot.respond(text, cancel=token)
                except Cancelled: result['cancelled'] = True
            except BaseException as error: errors.append(error)
            finally: bot.memory.close()
        thread = threading.Thread(target=run); thread.start()
        try:
            assert entered.wait(5)
            with writer.transaction():
                proceed.set()
                assert attempting.wait(5)  # Other connection now attempts BEGIN while lock is held.
                if change == 'cancel': token.cancel()
                else: writer.forget(fragment)
        finally:
            proceed.set(); thread.join(10)
        assert not thread.is_alive() and not errors, errors
        assert result == {'cancelled': True}
        assert store.list() == before
