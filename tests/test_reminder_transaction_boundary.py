"""Invalidation before local action transactions must prevent business writes."""
from contextlib import closing
import time

import pytest

from avatar.brain.memory import MemoryStore
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
