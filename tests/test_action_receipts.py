"""Evidence records originate in actual business transactions, never model text."""
from contextlib import closing
import json
import sqlite3
import time

import pytest

from avatar.brain.action_receipts import ActionReceiptStore, ReceiptContext
from avatar.brain.memory import MemoryStore
from avatar.brain.operations import OperationError
from avatar.brain.reminders import ReminderStore
from avatar.cancellation import CancellationToken, Cancelled
from avatar.main import Avatar


class NoModel:
    available = False


def source(memory):
    ident = memory.add_message('user', '提醒我明天下午3点私密事项', 'session')
    return ReceiptContext(ident, 'session', memory.context_revision)


def test_atomic_visibility_and_metadata_only(tmp_path):
    path = str(tmp_path/'db')
    with closing(MemoryStore(path)) as memory, closing(MemoryStore(path)) as observer:
        context = source(memory); reminders = ReminderStore(memory)
        with memory.transaction():
            reminder = reminders.create('提醒我明天下午3点私密事项', receipt_context=context)
            assert observer._conn.execute('SELECT count(*) FROM memory_reminders').fetchone()[0] == 0
            assert observer._conn.execute('SELECT count(*) FROM memory_action_receipts').fetchone()[0] == 0
        items = ActionReceiptStore(observer).read('new-server')['items']
        assert len(items) == 1 and items[0]['action'] == 'reminder.created'
        assert items[0]['reminder_id'] == reminder['id'] and items[0]['source_message_id'] == context.source_message_id
        assert items[0]['session_id'] == 'session' and '私密事项' not in json.dumps(items,ensure_ascii=False)


def test_receipt_insertion_failure_rolls_business_back(tmp_path):
    with closing(MemoryStore(str(tmp_path/'db'))) as memory:
        context = source(memory); store = ReminderStore(memory)
        memory._conn.execute("CREATE TRIGGER fail_receipt BEFORE INSERT ON memory_action_receipts BEGIN SELECT RAISE(ABORT,'receipt-failure'); END")
        with pytest.raises(sqlite3.IntegrityError,match='receipt-failure'):
            store.create('提醒我明天下午3点答辩', receipt_context=context)
        assert store.list() == []
        assert ActionReceiptStore(memory).read('server')['items'] == []


def test_outer_rollback_removes_business_and_receipt(tmp_path):
    with closing(MemoryStore(str(tmp_path/'db'))) as memory:
        context = source(memory); store = ReminderStore(memory)
        with pytest.raises(RuntimeError,match='fixture'):
            with memory.transaction():
                store.create('提醒我明天下午3点答辩', receipt_context=context)
                raise RuntimeError('fixture')
        assert store.list() == [] and ActionReceiptStore(memory).read('server')['items'] == []


@pytest.mark.parametrize('invalid',['missing','assistant','session','revision','redacted'])
def test_invalid_source_rolls_business_back(tmp_path,invalid):
    with closing(MemoryStore(str(tmp_path/'db'))) as memory:
        context = source(memory); ident = context.source_message_id
        if invalid == 'missing': ident += 100
        if invalid in ('assistant','redacted'):
            memory._conn.execute('UPDATE memory_messages SET '+('role=?' if invalid=='assistant' else 'content=?')+' WHERE id=?',
                                 ('assistant' if invalid=='assistant' else '[redacted]',ident));memory._conn.commit()
        context = ReceiptContext(ident,'wrong' if invalid=='session' else 'session',1 if invalid=='revision' else 0)
        store = ReminderStore(memory)
        with pytest.raises(Cancelled): store.create('提醒我明天下午3点答辩',receipt_context=context)
        assert store.list() == [] and ActionReceiptStore(memory).read('server')['items'] == []


def test_read_survives_reopen_filters_source_pages_and_does_not_write(tmp_path):
    path = str(tmp_path/'db')
    with closing(MemoryStore(path)) as memory:
        context = source(memory); store = ReminderStore(memory)
        one = store.create('提醒我明天下午3点答辩', receipt_context=context)
        store.set_status(one['id'],'cancelled',receipt_context=context)
        store.set_status(one['id'],'cancelled',receipt_context=context)  # No repeated transition receipt.
    with closing(MemoryStore(path)) as memory:
        reader = ActionReceiptStore(memory); changes=memory._conn.total_changes
        first = reader.read('restarted',limit=1,source_message_id=context.source_message_id)
        assert first['has_more'] and first['items'][0]['action']=='reminder.created'
        second=reader.read('restarted',after_id=first['next_after_id'])
        assert len(second['items'])==1 and second['items'][0]['action']=='reminder.cancelled'
        assert not second['has_more'] and not second['notification_delivery_verified']
        assert reader.read('server',source_message_id=999)['items']==[]
        assert memory._conn.total_changes==changes and not memory._conn.in_transaction


def test_due_claim_is_only_local_claim_and_legacy_store_does_not_invent_source(tmp_path):
    with closing(MemoryStore(str(tmp_path/'db'))) as memory:
        context = source(memory); store=ReminderStore(memory)
        item=store.create('提醒我明天下午3点答辩')
        assert ActionReceiptStore(memory).read('server')['items']==[]
        store.claim_due(now=item['due_at'],receipt_context=context)
        assert store.claim_due(now=item['due_at'],receipt_context=context)==[]
        data=ActionReceiptStore(memory).read('server')
        assert [r['action'] for r in data['items']]==['reminder.claimed_due']
        assert not data['notification_delivery_verified']


def test_forget_hides_previous_evidence_and_stale_revision_conflicts(tmp_path):
    with closing(MemoryStore(str(tmp_path/'db'))) as memory:
        private=memory.remember_user('名字','回执隐私名');context=source(memory)
        ReminderStore(memory).create('提醒我明天下午3点答辩',receipt_context=context)
        memory.forget(private)
        reader=ActionReceiptStore(memory)
        assert reader.read('server')['items']==[]
        with pytest.raises(OperationError) as error:reader.read('server',revision=0)
        assert error.value.status==409


def test_reply_cancel_after_business_commit_keeps_real_receipt(tmp_path):
    bot=Avatar(db_path=str(tmp_path/'db'),llm=NoModel());token=CancellationToken()
    original=bot.reminders.create
    def committed(*args,**kwargs):
        result=original(*args,**kwargs);token.cancel();return result
    bot.reminders.create=committed
    try:
        with pytest.raises(Cancelled):bot.respond('提醒我明天下午3点答辩',cancel=token)
        data=ActionReceiptStore(bot.memory).read('server')
        assert len(bot.reminders.list())==1 and [r['action'] for r in data['items']]==['reminder.created']
        assert bot.memory._conn.execute("SELECT count(*) FROM memory_messages WHERE role='assistant'").fetchone()[0]==0
    finally:bot.memory.close()


def test_successful_avatar_includes_actual_receipts_not_generated_claims(tmp_path):
    bot=Avatar(db_path=str(tmp_path/'db'),llm=NoModel())
    try:
        created=bot.respond('提醒我明天下午3点答辩')
        assert [r['action'] for r in created['action_receipts']['items']]==['reminder.created']
        assert created['action_receipts']['items'][0]['source_message_id']==created['conversation']['user_message_id']
        ordinary=bot.respond('请帮我发短信')
        assert ordinary['action_receipts']['items']==[]
    finally:bot.memory.close()


@pytest.mark.parametrize('option',[{'limit':0},{'limit':201},{'limit':True},{'after_id':-1},
                                 {'source_message_id':0},{'revision':-1}])
def test_bad_read_parameters(tmp_path,option):
    with closing(MemoryStore(str(tmp_path/'db'))) as memory:
        with pytest.raises(OperationError) as error:ActionReceiptStore(memory).read('server',**option)
        assert error.value.status==422
