"""Read current persisted messages; store only revision-bound original results."""
import json

from ..cancellation import Cancelled
from .operations import OperationError


class ConversationStore:
    def __init__(self, memory):
        self.memory = memory
        self.conn = memory._conn

    def record_result(self, result):
        source = result.get('conversation')
        if not source:
            return
        with self.memory.transaction():
            if self.memory.context_revision != source['revision']:
                raise Cancelled('context changed before public conversation result')
            rows = self.conn.execute(
                'SELECT id,role,content,session_id FROM memory_messages WHERE id IN (?,?)',
                (source['user_message_id'], source['assistant_message_id'])).fetchall()
            by_id = {row['id']: row for row in rows}
            user, assistant = by_id.get(source['user_message_id']), by_id.get(source['assistant_message_id'])
            if (not user or not assistant or user['role'] != 'user' or assistant['role'] != 'assistant'
                    or user['content'] == '[redacted]' or assistant['content'] != result['reply']
                    or user['session_id'] != source['session_id'] or assistant['session_id'] != source['session_id']):
                raise Cancelled('conversation sources changed before result commit')
            self.conn.execute('INSERT OR REPLACE INTO memory_chat_results VALUES (?,?,?)',
                              (assistant['id'], source['revision'], json.dumps(result, ensure_ascii=False, allow_nan=False)))

    def read(self, instance_id, *, limit=100, before_id=None, revision=None):
        # A short read transaction binds all rows and their traces to one DB
        # snapshot. It is released before HTTP serialization or network IO.
        owned = not self.conn.in_transaction
        if owned:
            self.conn.execute('BEGIN')
        try:
            current = self.memory.context_revision
            if revision is not None and revision != current:
                raise OperationError(409, 'conversation_changed', '记忆已更新，请重新读取对话记录。')
            where, params = "m.role IN ('user','assistant')", []
            if before_id is not None:
                where += ' AND m.id<?'
                params.append(before_id)
            rows = self.conn.execute(
                'SELECT m.*,r.context_revision,r.result_json FROM memory_messages m '
                'LEFT JOIN memory_chat_results r ON r.message_id=m.id WHERE '+where+
                ' ORDER BY m.id DESC LIMIT ?', [*params, limit + 1]).fetchall()
            has_more = len(rows) > limit
            items = []
            for row in reversed(rows[:limit]):
                redacted = row['content'] == '[redacted]'
                item = {key: row[key] for key in ['id', 'role', 'session_id', 'created_at']}
                item.update(text='此条内容已删除。' if redacted else row['content'], redacted=redacted)
                if row['role'] == 'assistant' and not redacted and row['context_revision'] == current and row['result_json']:
                    try:
                        result = json.loads(row['result_json'])
                        if isinstance(result, dict) and result.get('reply') == row['content']:
                            item['result'] = result
                    except (ValueError, TypeError):
                        pass
                items.append(item)
            result = {'instance_id': instance_id, 'revision': current, 'items': items, 'has_more': has_more,
                      'next_before_id': items[0]['id'] if has_more and items else None}
            if owned:
                self.conn.commit()
            return result
        except BaseException:
            if owned:
                self.conn.rollback()
            raise
