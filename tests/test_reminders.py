from datetime import datetime, timezone, timedelta

import pytest

from avatar.brain.memory import MemoryStore
from avatar.brain.reminders import ReminderStore, parse_reminder


TZ = timezone(timedelta(hours=8))
NOW = datetime(2026, 11, 1, 10, tzinfo=TZ).timestamp()


@pytest.mark.parametrize('text, expected, title', [
    ('提醒我明天下午3点答辩', (2026, 11, 2, 15, 0), '答辩'),
    ('请提醒我后天早上8点半交作业', (2026, 11, 3, 8, 30), '交作业'),
    ('提醒我下周一上午9点开会', (2026, 11, 2, 9, 0), '开会'),
    ('提醒我2026年12月1日晚上8点打电话', (2026, 12, 1, 20, 0), '打电话'),
])
def test_explicit_chinese_reminder(text, expected, title):
    result = parse_reminder(text, now=NOW)
    assert result['due_at'] == datetime(*expected, tzinfo=TZ).timestamp()
    assert result['title'] == title


@pytest.mark.parametrize('text', [
    '我明天下午3点答辩', '假如提醒我明天下午3点答辩',
    '他说“提醒我明天下午3点答辩”', '别提醒我明天下午3点答辩',
])
def test_only_explicit_request_creates_reminder(text):
    assert parse_reminder(text, now=NOW) is None


@pytest.mark.parametrize('text', [
    '提醒我明天答辩', '提醒我2027年2月30日8点开会',
    '提醒我明天25点开会', '提醒我今天早上8点开会',
    '提醒我明天下午3点', '提醒我明天3点和后天4点开会',
    '提醒我明天3点半', '提醒我明天3点15分', '提醒我明天3点30',
])
def test_invalid_or_ambiguous_time_requires_clarification(text):
    with pytest.raises(ValueError):
        parse_reminder(text, now=NOW)


def test_claim_once_across_connections_cancel_and_delete(tmp_path):
    path = str(tmp_path / 'memory.db')
    memory = MemoryStore(path)
    store = ReminderStore(memory)
    row = store.create('提醒我明天下午3点答辩', now=NOW)
    cancelled = store.create('提醒我明天下午3点开会', now=NOW)
    store.set_status(cancelled['id'], 'cancelled')
    due = row['due_at']
    assert store.claim_due(now=due - 1) == []
    memory.close()
    a, b = MemoryStore(path), MemoryStore(path)
    assert [r['id'] for r in ReminderStore(a).claim_due(now=due)] == [row['id']]
    assert ReminderStore(b).claim_due(now=due) == []
    ReminderStore(a).set_status(row['id'], 'completed')
    assert ReminderStore(b).list()[0]['status'] == 'completed'
    ReminderStore(a).delete(row['id'])
    assert len(ReminderStore(b).list()) == 1
    with pytest.raises(ValueError):
        ReminderStore(a).set_status(999, 'completed')
    a.close()
    b.close()
