"""Source/transaction/state controls for explicit reminder reads, no model calls."""
from contextlib import closing
from dataclasses import replace
import time

import pytest

from avatar.brain.memory import MemoryStore
from avatar.brain.reminders import ReminderStore
from avatar.brain.reminder_queries import ReminderQuery, QuerySource, parse_query, resolve_query
from avatar.cancellation import CancellationToken, Cancelled


@pytest.mark.parametrize('text,expected', [
    ('查询提醒编号1', ReminderQuery('status', 1)), (' 查看提醒#2状态。 ', ReminderQuery('status', 2)),
    ('请查看提醒003号状态！', ReminderQuery('status', 3)), ('查询提醒9223372036854775807', ReminderQuery('status', 2**63-1)),
    ('查询提醒运行条件', ReminderQuery('conditions')), ('请查看提醒送达条件？', ReminderQuery('conditions')),
    ('查询提醒编号0', ReminderQuery('invalid')), ('查询提醒-1', ReminderQuery('invalid')),
    ('查询提醒9223372036854775808', ReminderQuery('invalid')), ('查询提醒'+'1'*100, ReminderQuery('invalid')),
    ('查询提醒编号１', ReminderQuery('invalid')), ('查询提醒\n1', ReminderQuery('invalid')),
    ('查询提醒1，然后取消提醒1', ReminderQuery('invalid')), ('“查询提醒编号1”', None),
    ('请写一句“查询提醒编号1”', None), ('回到现实，查询提醒编号1', None), ('提醒我明天九点复习', None), ('查看提醒', None),
])
def test_bounded_command_syntax(text, expected):
    assert parse_query(text) == expected


def prepare(memory, text='查询提醒编号1'):
    store = ReminderStore(memory)
    now = time.time()
    memory._conn.execute('INSERT INTO memory_reminders(title,due_at,created_at) VALUES (?,?,?)', ('受控提醒', now-60, now-3600))
    memory._conn.commit()
    ident = memory.add_message('user', text, 'session')
    return store, QuerySource(ident, 'session', memory.context_revision, 'current_user', True)


def projection(memory):
    return [list(memory._conn.execute('SELECT * FROM '+name)) for name in (
        'memory_reminders', 'memory_reminder_deliveries', 'memory_action_receipts')]


@pytest.mark.parametrize('status', ['active', 'cancelled', 'completed'])
def test_real_current_status_legacy_without_receipt_and_no_business_writes(status):
    with closing(MemoryStore(':memory:')) as memory:
        store, source = prepare(memory)
        memory._conn.execute('UPDATE memory_reminders SET status=?', (status,)); memory._conn.commit()
        before = projection(memory); changes = memory._conn.total_changes
        result = resolve_query(store, parse_query('查询提醒编号1'), '查询提醒编号1', source)
        assert result.metadata['state']['status'] == status and result.metadata['exists']
        assert result.metadata['human_reading_verified'] is False
        assert not result.metadata['state']['service_claim_recorded'] and not result.metadata['state']['client_ack_recorded']
        assert projection(memory) == before and memory._conn.total_changes == changes
        assert not memory._conn.in_transaction


def test_read_does_not_claim_due_but_explicit_later_poll_still_works():
    with closing(MemoryStore(':memory:')) as memory:
        store, source = prepare(memory)
        result = resolve_query(store, parse_query('查询提醒编号1'), '查询提醒编号1', source)
        assert not result.metadata['state']['service_claim_recorded']
        pending = store.pending_deliveries()
        assert len(pending) == 1 and len(store.pending_deliveries()) == 1
        result = resolve_query(store, parse_query('查询提醒编号1'), '查询提醒编号1', source)
        assert result.metadata['state']['service_claim_recorded'] and not result.metadata['state']['client_ack_recorded']
        store.acknowledge_delivery(pending[0]['delivery_id'], expected_revision=source.revision)
        result = resolve_query(store, parse_query('查询提醒编号1'), '查询提醒编号1', source)
        assert result.metadata['state']['client_ack_recorded'] and not result.metadata['human_reading_verified']
        assert '不代表已阅读' in result.reply


@pytest.mark.parametrize('text', ['查看提醒送达条件', '查询提醒编号0', '查询提醒编号99'])
def test_conditions_invalid_and_missing_are_readonly_and_do_not_invent_history(text):
    with closing(MemoryStore(':memory:')) as memory:
        store, source = prepare(memory, text)
        before = projection(memory)
        result = resolve_query(store, parse_query(text), text, source)
        assert projection(memory) == before and not result.metadata['business_mutations']
        assert not result.metadata['human_reading_verified']
        if text == '查看提醒送达条件':
            assert result.metadata['requires_running_server'] and result.metadata['web_requires_active_client_polling']
            assert result.metadata['external_delivery_channels'] == [] and '服务退出期间无法自动投递' in result.reply
        if text == '查询提醒编号99':
            assert result.metadata['exists'] is False and '从未' not in result.reply


@pytest.mark.parametrize('mutation', ['missing','role','content','session','revision','scope','mixed','bool_id','bool_revision','forged_command'])
def test_source_or_authority_mismatch_cancels_without_business_mutation(mutation):
    with closing(MemoryStore(':memory:')) as memory:
        text = '查询提醒编号1'; store, source = prepare(memory, text); command = parse_query(text)
        if mutation == 'missing':
            source = replace(source, source_message_id=999)
        elif mutation in ('role','content','session'):
            field = {'role':'role','content':'content','session':'session_id'}[mutation]
            memory._conn.execute('UPDATE memory_messages SET '+field+'=? WHERE id=?', ('wrong',source.source_message_id)); memory._conn.commit()
        elif mutation == 'revision': source = replace(source, revision=source.revision+1)
        elif mutation == 'scope': source = replace(source, scope='fictional_character',turn_tools_allowed=False)
        elif mutation == 'mixed': source = replace(source, turn_tools_allowed=False)
        elif mutation == 'bool_id': source = replace(source, source_message_id=True)
        elif mutation == 'bool_revision': source = replace(source, revision=False)
        elif mutation == 'forged_command': command = ReminderQuery('status',2)
        before = projection(memory)
        with pytest.raises(Cancelled): resolve_query(store,command,text,source)
        assert projection(memory) == before


def test_caller_transaction_owned_and_cancel_releases_only_own_snapshot():
    with closing(MemoryStore(':memory:')) as memory:
        text = '查询提醒编号1'; store, source = prepare(memory,text)
        with memory.transaction():
            resolve_query(store,parse_query(text),text,source)
            assert memory._conn.in_transaction
        token = CancellationToken(); token.cancel()
        with pytest.raises(Cancelled): resolve_query(store,parse_query(text),text,source,checkpoint=token.checkpoint)
        assert not memory._conn.in_transaction


@pytest.mark.parametrize('value', ['invalid-date', 1e300])
def test_corrupt_stored_date_reports_unavailable_instead_of_false_absence(value):
    with closing(MemoryStore(':memory:')) as memory:
        text = '查询提醒编号1'; store, source = prepare(memory,text)
        memory._conn.execute('UPDATE memory_reminders SET due_at=?',(value,)); memory._conn.commit()
        result = resolve_query(store,parse_query(text),text,source)
        assert result.metadata['exists'] and result.metadata['state'] is None
        assert result.metadata['state_error']=='stored_reminder_state_unavailable'
        assert '暂时无法可靠读取' in result.reply
