"""Explicit prospective memory. China time, seconds, local delivery only."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re
import time


CHINA = timezone(timedelta(hours=8))
_DATE = r'(?:\d{4}年\d{1,2}月\d{1,2}[日号]|今天|明天|后天|(?:下周|这周|周|星期)[一二三四五六日天])'
_CHINESE_CLOCK = r'[零〇一二两三四五六七八九十]+'
_TIME = (rf'(?P<period>早上|上午|下午|晚上|中午)?(?P<hour>\d{{1,2}}|{_CHINESE_CLOCK})[点时]'
         rf'(?:(?P<half>半)(?!个?(?:小时|分钟))|'
         rf'(?P<minute>\d+)(?:分(?!钟)|(?![\d分A-Za-z_]))|'
         rf'(?P<chinese_minute>{_CHINESE_CLOCK})分(?!钟))?')


def _clock_number(value: str) -> int:
    # Convert only parsed clock fields. Never translate the user's task title.
    if value.isdecimal():
        return int(value)
    digits = {character: number for number, character in enumerate('零一二三四五六七八九')}
    digits.update({'〇': 0, '两': 2})
    if value in digits:
        return digits[value]
    if re.fullmatch(r'[零〇][一二三四五六七八九]', value):
        return digits[value[-1]]
    if re.fullmatch(r'(?:[二三四五六七八九]?十[一二三四五六七八九]?)', value):
        tens, ones = value.split('十')
        return (digits[tens] if tens else 1) * 10 + (digits[ones] if ones else 0)
    raise ValueError('钟点无效。')


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
    # Bare quantities/durations are not a task. Keep duration or identifier
    # prefixes with their actual task instead of consuming them as clock fields.
    if re.fullmatch(rf'(?:\d+|{_CHINESE_CLOCK})(?:小时|分钟)?|半(?:个)?(?:小时|分钟)', title):
        raise ValueError('请提供一个明确事项。')
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
    hour = _clock_number(parsed['hour'])
    minute = 30 if parsed['half'] else _clock_number(parsed['minute'] or parsed['chinese_minute'] or '0')
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
        # Metadata only: current titles stay in the original business table.
        # No backfill: historical claims never become fabricated confirmations.
        self.conn.execute('''CREATE TABLE IF NOT EXISTS memory_reminder_deliveries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reminder_id INTEGER NOT NULL UNIQUE,
            created_at REAL NOT NULL, acknowledged_at REAL
        )''')
        self.memory._commit()

    def create(self, text: str, *, now: float | None = None, checkpoint=None, receipt_context=None) -> dict:
        data = parse_reminder(text, now=now)
        if data is None:
            raise ValueError('请用“提醒我……”明确创建提醒。')
        with self.memory.transaction():
            if checkpoint is not None:
                checkpoint()
            cur = self.conn.execute(
                'INSERT INTO memory_reminders(title,due_at,created_at) VALUES (?,?,?)',
                (data['title'], data['due_at'], time.time() if now is None else now))
            if receipt_context is not None:
                from .action_receipts import ActionReceiptStore
                ActionReceiptStore(self.memory).record_reminder(receipt_context, 'reminder.created', cur.lastrowid)
            return dict(self.conn.execute('SELECT * FROM memory_reminders WHERE id=?', (cur.lastrowid,)).fetchone())

    def list(self) -> list[dict]:
        return [dict(row) for row in self.conn.execute('SELECT * FROM memory_reminders ORDER BY id')]

    def list_with_delivery(self) -> list[dict]:
        """Management view; ACK is a client report, never proof of reading."""
        return [dict(row) for row in self.conn.execute(
            'SELECT r.*,d.acknowledged_at AS delivery_acknowledged_at '
            'FROM memory_reminders r LEFT JOIN memory_reminder_deliveries d ON d.reminder_id=r.id '
            'ORDER BY r.id')]

    def set_status(self, reminder_id: int, status: str, *, checkpoint=None, receipt_context=None) -> None:
        if status not in ('completed', 'cancelled'):
            raise ValueError('status must be completed or cancelled')
        with self.memory.transaction():
            if checkpoint is not None:
                checkpoint()
            previous = self.conn.execute('SELECT status FROM memory_reminders WHERE id=?', (reminder_id,)).fetchone()
            cur = self.conn.execute('UPDATE memory_reminders SET status=? WHERE id=?', (status, reminder_id))
            if not cur.rowcount:
                raise ValueError('reminder does not exist')
            if receipt_context is not None and previous['status'] != status:
                from .action_receipts import ActionReceiptStore
                ActionReceiptStore(self.memory).record_reminder(receipt_context, 'reminder.'+status, reminder_id)

    def delete(self, reminder_id: int) -> None:
        with self.memory.transaction():
            self.conn.execute('DELETE FROM memory_reminder_deliveries WHERE reminder_id=?', (reminder_id,))
            self.conn.execute('DELETE FROM memory_reminders WHERE id=?', (reminder_id,))

    def claim_due(self, *, now: float | None = None, checkpoint=None, receipt_context=None) -> list[dict]:
        """Atomically claim once across connections; no external notification side effects.

        This return value is at-most-once, not proof of display. The same
        transaction enqueues a durable client event for pending_deliveries().
        Older than 24h stays listed but will not interrupt a later conversation.
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
                self.conn.execute(
                    'INSERT INTO memory_reminder_deliveries(reminder_id,created_at) VALUES (?,?)',
                    (row['id'], now))
                if receipt_context is not None:
                    from .action_receipts import ActionReceiptStore
                    ActionReceiptStore(self.memory).record_reminder(receipt_context, 'reminder.claimed_due', row['id'])
            return [dict(row, notified_at=now) for row in rows]


    def pending_deliveries(self, *, now: float | None = None) -> list[dict]:
        """Replay eligible unacknowledged client events, including SDK claims.

        Responses may repeat across pages/connections until explicit ACK. This
        does not provide exactly-once perception or any external notification.
        """
        now = time.time() if now is None else now
        with self.memory.transaction():
            self.claim_due(now=now)
            return [dict(row) for row in self.conn.execute(
                "SELECT r.*,d.id AS delivery_id,d.created_at AS delivery_created_at "
                "FROM memory_reminder_deliveries d JOIN memory_reminders r ON r.id=d.reminder_id "
                "WHERE d.acknowledged_at IS NULL AND r.status='active' "
                'AND r.due_at BETWEEN ? AND ? ORDER BY r.due_at,r.id', (now-86400,now))]

    def acknowledge_delivery(self, delivery_id: int, *, expected_revision: int,
                             now: float | None = None) -> dict:
        """Record an explicit client acknowledgement, never a human-read proof.

        Version check and first timestamp update share SQLite's writer lock.
        A duplicate is idempotent while its reminder remains eligible.
        """
        if (type(delivery_id) is not int or not 0 < delivery_id <= 2**63-1
                or type(expected_revision) is not int or not 0 <= expected_revision <= 2**63-1):
            raise ValueError('invalid_delivery_ack')
        now = time.time() if now is None else now
        with self.memory.transaction():
            if self.memory.context_revision != expected_revision:
                raise ValueError('delivery_revision_changed')
            row = self.conn.execute(
                "SELECT d.* FROM memory_reminder_deliveries d "
                "JOIN memory_reminders r ON r.id=d.reminder_id "
                "WHERE d.id=? AND r.status='active' AND r.due_at BETWEEN ? AND ?",
                (delivery_id, now-86400, now)).fetchone()
            if row is None:
                raise ValueError('delivery_not_pending')
            if row['acknowledged_at'] is None:
                self.conn.execute('UPDATE memory_reminder_deliveries SET acknowledged_at=? WHERE id=?',
                                  (now, delivery_id))
            return dict(self.conn.execute('SELECT * FROM memory_reminder_deliveries WHERE id=?',
                                          (delivery_id,)).fetchone())
