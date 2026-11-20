"""Actual SQL list snapshots, bounded reads and historical-context separation."""
from contextlib import closing
import time

import pytest

from avatar.brain.memory import MemoryStore
from avatar.brain.reminders import ReminderStore
from avatar.brain.reminder_queries import QuerySource, parse_query, resolve_query
from avatar.main import Avatar
from test_capability_prompt_lab import Recorder


def test_automatic_numbered_query_enters_context_as_historical_snapshot():
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=Recorder('不应调用'))
        bot.respond('查询提醒编号1')
        assert '历史提醒查询快照' in memory.get_short_term()[-1]['content']
        assert '不是当前状态' in memory.get_short_term()[-1]['content']


@pytest.mark.parametrize('text', [
    '“列出提醒”', '请写一句列出提醒', '列出提醒并取消提醒1',
    '我很担心，列出提醒', '列出提醒？然后发给老师',
])
def test_list_alias_does_not_capture_quoted_mixed_or_action_requests(text):
    assert parse_query(text) is None


def test_actual_list_is_bounded_counts_all_statuses_and_does_not_commit_caller():
    with closing(MemoryStore(':memory:')) as memory:
        store = ReminderStore(memory)
        for index in range(23):
            memory._conn.execute('INSERT INTO memory_reminders(title,due_at,created_at,status) VALUES (?,?,?,?)',
                (f'事项{index}', time.time()+600, time.time(), ['active','cancelled','completed'][index % 3]))
        memory._conn.commit()
        ident = memory.add_message('user', '列出提醒', 'source')
        context = QuerySource(ident, 'source', memory.context_revision, 'current_user', True)
        changes = memory._conn.total_changes
        memory._conn.execute('BEGIN')
        try:
            answer = resolve_query(store, parse_query('列出提醒'), '列出提醒', context)
            assert memory._conn.in_transaction and memory._conn.total_changes == changes
        finally:
            memory._conn.rollback()
        data = answer.metadata
        assert data['record_count'] == 23 and len(data['records']) == 20 and data['has_more']
        assert {r['status'] for r in data['records']} == {'active','cancelled','completed'}
        assert not data['business_mutations'] and not data['human_reading_verified']
        assert '23' in answer.reply and '20' in answer.reply and '已阅读' in answer.reply
        assert not memory._conn.execute('SELECT 1 FROM memory_action_receipts').fetchone()


def test_role_list_does_not_read_real_reminder_records():
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=Recorder('不应猜本机状态'))
        bot.respond('我来扮演小说角色。')
        result = bot.respond('列出提醒')
        assert result['generation_mode'] == 'rules_speaker_scope'
        assert '未授权读取' in result['reply']


def test_empty_snapshot_is_actual_absence_without_permanent_or_delivery_claim():
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=Recorder('我已发短信提醒'))
        result = bot.respond('列出提醒')
        assert result['reminder_query']['record_count'] == 0
        assert not result['reminder_query']['has_more']
        assert '当前' in result['reply'] and '从未' not in result['reply']
