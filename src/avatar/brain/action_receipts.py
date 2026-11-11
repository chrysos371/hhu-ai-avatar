"""SQL action evidence, independent of generated reply success or wording."""
from dataclasses import dataclass
import time

from ..cancellation import Cancelled
from .operations import OperationError


@dataclass(frozen=True)
class ReceiptContext:
    source_message_id: int
    session_id: str
    revision: int


class ActionReceiptStore:
    def __init__(self, memory):
        self.memory = memory
        self.conn = memory._conn

    def record_reminder(self, context, action, reminder_id):
        """Called only inside the business write transaction; never commits it."""
        if not self.conn.in_transaction or self.memory._transaction_depth < 1:
            raise RuntimeError('Action evidence requires the owning business transaction')
        if action not in {'reminder.created', 'reminder.cancelled', 'reminder.completed', 'reminder.claimed_due'}:
            raise ValueError('Unsupported local action receipt')
        source = self.conn.execute('SELECT role,session_id,content FROM memory_messages WHERE id=?',
                                   (context.source_message_id,)).fetchone()
        if (self.memory.context_revision != context.revision or not source or source['role'] != 'user'
                or source['session_id'] != context.session_id or source['content'] == '[redacted]'):
            raise Cancelled('Action receipt source is no longer current')
        self.conn.execute('''INSERT INTO memory_action_receipts
            (source_message_id,session_id,context_revision,action,reminder_id,recorded_at)
            VALUES (?,?,?,?,?,?)''', (context.source_message_id, context.session_id, context.revision,
                                     action, reminder_id, time.time()))

    def read(self, instance_id, *, revision=None, source_message_id=None, after_id=0, limit=100):
        if (type(limit) is not int or not 1 <= limit <= 200 or type(after_id) is not int
                or not 0 <= after_id <= 2**63-1
                or revision is not None and (type(revision) is not int or not 0 <= revision <= 2**63-1)
                or source_message_id is not None and (type(source_message_id) is not int
                                                      or not 0 < source_message_id <= 2**63-1)):
            raise OperationError(422, 'invalid_action_receipts_query')
        # Release the snapshot before serialization; no migration or writes here.
        owned = not self.conn.in_transaction
        if owned: self.conn.execute('BEGIN')
        try:
            current = self.memory.context_revision
            if revision is not None and revision != current:
                raise OperationError(409, 'action_receipts_changed', '记忆已更新，请重新读取操作记录。')
            where = 'r.context_revision=? AND r.id>?'
            values = [current, after_id]
            if source_message_id is not None:
                where += ' AND r.source_message_id=?'; values.append(source_message_id)
            rows = self.conn.execute('''SELECT r.* FROM memory_action_receipts r
                JOIN memory_messages m ON m.id=r.source_message_id AND m.role='user'
                    AND m.session_id=r.session_id AND m.content!='[redacted]'
                WHERE '''+where+' ORDER BY r.id LIMIT ?', [*values, limit+1]).fetchall()
            items = [dict(row) for row in rows[:limit]]
            result = {'instance_id': instance_id, 'revision': current, 'items': items,
                      'has_more': len(rows)>limit, 'next_after_id': items[-1]['id'] if len(rows)>limit else None,
                      'scope': 'current_visible_local_sql_receipts', 'notification_delivery_verified': False}
            if owned: self.conn.commit()
            return result
        except BaseException:
            if owned: self.conn.rollback()
            raise
