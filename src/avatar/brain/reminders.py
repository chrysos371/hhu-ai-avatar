"""Explicit prospective memory. China time, seconds, local delivery only."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
import time


CHINA = timezone(timedelta(hours=8))
_DATE = r'(?:\d{4}年\d{1,2}月\d{1,2}[日号]|今天|明天|后天|(?:下周|这周|周|星期)[一二三四五六日天])'
_TIME = r'(?P<period>早上|上午|下午|晚上|中午)?(?P<hour>\d{1,2})[点时](?:(?P<half>半)|(?P<minute>\d{1,2})分?)?'


def parse_reminder(text: str, *, now: float | None = None) -> dict | None:
    match = re.match(r'^(?:请)?提醒我\s*(.*)$', text.strip())
    if not match:
        return None
    body = match[1]
    # Parse the complete time before looking for a title. Requiring a title in
    # the same regex would backtrack "3点半" into hour=3/title="半".
    parsed = re.match(rf'(?P<date>{_DATE})\s*{_TIME}', body)
    title = body[parsed.end():].strip(' ，。！!') if parsed else ''
    if not parsed or not title or re.search(_DATE, title):
        raise ValueError('请明确一个日期、钟点和事项，例如：提醒我明天下午3点答辩。')
    current = datetime.fromtimestamp(time.time() if now is None else now, CHINA)
    date_text = parsed['date']
    if '年' in date_text:
        year, month, day = map(int, re.findall(r'\d+', date_text))
        target = datetime(year, month, day, tzinfo=CHINA)
    elif date_text in ('今天', '明天', '后天'):
        target = current + timedelta(days={'今天': 0, '明天': 1, '后天': 2}[date_text])
    else:
        weekday = '一二三四五六日'.index(date_text[-1].replace('天', '日'))
        if date_text.startswith('下周'):
            days = 7 - current.weekday() + weekday
        elif date_text.startswith('这周'):
            days = weekday - current.weekday()
        else:
            days = (weekday - current.weekday()) % 7
        target = current + timedelta(days=days)
    hour = int(parsed['hour'])
    minute = 30 if parsed['half'] else int(parsed['minute'] or 0)
    period = parsed['period']
    if hour > 23 or minute > 59 or (period and not 1 <= hour <= 12):
        raise ValueError('钟点无效。')
    if period in ('下午', '晚上', '中午') and hour < 12:
        hour += 12
    if period in ('早上', '上午') and hour == 12:
        hour = 0
    target = target.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= current:
        raise ValueError('提醒时间已过去，请指定将来的时间。')
    if not title or title.startswith(('和后天', '和明天')):
        raise ValueError('请提供一个明确事项。')
    return {'title': title, 'due_at': target.timestamp()}


class ReminderStore:
    def __init__(self, memory):
        self.memory = memory
        self.conn = memory._conn
        self.conn.execute('''CREATE TABLE IF NOT EXISTS memory_reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL, due_at REAL NOT NULL, created_at REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'active', notified_at REAL
        )''')
        self.memory._commit()

    def create(self, text: str, *, now: float | None = None, checkpoint=None) -> dict:
        data = parse_reminder(text, now=now)
        if data is None:
            raise ValueError('请用“提醒我……”明确创建提醒。')
        with self.memory.transaction():
            if checkpoint is not None:
                checkpoint()
            cur = self.conn.execute(
                'INSERT INTO memory_reminders(title,due_at,created_at) VALUES (?,?,?)',
                (data['title'], data['due_at'], time.time() if now is None else now))
            return dict(self.conn.execute('SELECT * FROM memory_reminders WHERE id=?', (cur.lastrowid,)).fetchone())

    def list(self) -> list[dict]:
        return [dict(row) for row in self.conn.execute('SELECT * FROM memory_reminders ORDER BY id')]

    def set_status(self, reminder_id: int, status: str, *, checkpoint=None) -> None:
        if status not in ('completed', 'cancelled'):
            raise ValueError('status must be completed or cancelled')
        with self.memory.transaction():
            if checkpoint is not None:
                checkpoint()
            cur = self.conn.execute('UPDATE memory_reminders SET status=? WHERE id=?', (status, reminder_id))
            if not cur.rowcount:
                raise ValueError('reminder does not exist')

    def delete(self, reminder_id: int) -> None:
        with self.memory.transaction():
            self.conn.execute('DELETE FROM memory_reminders WHERE id=?', (reminder_id,))

    def claim_due(self, *, now: float | None = None, checkpoint=None) -> list[dict]:
        """Atomically claim once across connections; no external notification side effects.

        Delivery is at-most-once, not acknowledged delivery. Older than 24h stays
        visible in the list but will not interrupt a later conversation.
        """
        now = time.time() if now is None else now
        with self.memory.transaction():
            if checkpoint is not None:
                checkpoint()
            # A write first acquires SQLite's writer lock before selecting.
            self.conn.execute('UPDATE memory_reminders SET notified_at=notified_at WHERE 0')
            rows = self.conn.execute(
                "SELECT * FROM memory_reminders WHERE status='active' AND notified_at IS NULL "
                'AND due_at BETWEEN ? AND ? ORDER BY due_at,id', (now - 86400, now)).fetchall()
            for row in rows:
                self.conn.execute('UPDATE memory_reminders SET notified_at=? WHERE id=?', (now, row['id']))
            return [dict(row, notified_at=now) for row in rows]
