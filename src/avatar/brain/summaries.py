"""Bounded extractive conversation summaries with durable source IDs.

No generated facts, no assistant output, no recursive summarization. Identity
and preferences belong to current versioned facts, not this discussion context.
"""
from __future__ import annotations

import json
import re
from .facts import safe_context_source


_UNSAFE = re.compile(r'假如|假设|假使|如果|也许|可能|朋友|他说|她说|[“”"「」『』？?]|忽略.{0,20}(?:系统|指令)|系统提示|\[redacted\]', re.I)
_ANCHORS = ('方案', '代号', '主题', '预算', '时长', '约束', '顺序', '截止', '目标', '项目',
            '课题', '正在', '准备', '决定', '要求', '计划')
_SAFE_SOURCE = '''NOT EXISTS (
    SELECT 1 FROM memory_sources s JOIN memory_fragments f ON f.id=s.fragment_id
    WHERE s.source_message_id=m.id AND (f.status!='active' OR f.profile_key IS NOT NULL
                                         OR f.memory_type IN ('user_profile','preference'))
)'''


class SummaryStore:
    def __init__(self, memory, *, max_chars: int = 1600, max_items: int = 8):
        if type(max_chars) is not int or not 256 <= max_chars <= 8000:
            raise ValueError('summary budget must be 256..8000 characters')
        if type(max_items) is not int or not 1 <= max_items <= 16:
            raise ValueError('summary max_items must be 1..16')
        self.memory = memory
        self.conn = memory._conn
        self.max_chars, self.max_items = max_chars, max_items

    @staticmethod
    def _eligible(row) -> bool:
        return (len(row['content'].strip()) >= 6 and not _UNSAFE.search(row['content'])
                and safe_context_source(row['content']))

    def _bounded(self, rows) -> list[dict]:
        items = []
        for row in rows:
            if not self._eligible(row):
                continue
            item = dict(message_id=row['id'], text=row['content'][:180], created_at=row['created_at'])
            if len(json.dumps(items + [item], ensure_ascii=False)) <= self.max_chars:
                items.append(item)
            if len(items) >= self.max_items:
                break
        return items

    def read(self, session_id: str) -> dict:
        # Always recheck live source content and status, even if another
        # connection corrected or redacted it since the summary was built.
        rows = self.conn.execute(
            'SELECT m.* FROM memory_summary_items i JOIN memory_messages m ON m.id=i.source_message_id '
            "WHERE i.session_id=? AND m.session_id=i.session_id AND m.role='user' AND " + _SAFE_SOURCE +
            ' ORDER BY m.id', (session_id,)).fetchall()
        items = self._bounded(rows)
        return dict(session_id=session_id, kind='source_excerpts', items=items,
                    characters=len(json.dumps(items, ensure_ascii=False)), max_characters=self.max_chars)

    def refresh(self, session_id: str) -> dict:
        with self.memory.transaction():
            # Acquire a writer lock before reading, so deletion/correction
            # cannot race a stale snapshot into the durable selection.
            self.conn.execute('DELETE FROM memory_summary_items WHERE 0')
            cutoff = self.conn.execute(
                'SELECT id FROM memory_messages WHERE session_id=? ORDER BY id DESC LIMIT 1 OFFSET ?',
                (session_id, max(0, self.memory.short_term_limit - 1))).fetchone()
            rows = []
            if cutoff is not None:
                rows = self.conn.execute(
                    "SELECT m.* FROM memory_messages m WHERE m.session_id=? AND m.role='user' "
                    'AND m.id<? AND ' + _SAFE_SOURCE + ' ORDER BY m.id DESC LIMIT 200',
                    (session_id, cutoff['id'])).fetchall()
            ranked = sorted(rows, key=lambda r: (sum(word in r['content'] for word in _ANCHORS), r['id']), reverse=True)
            items = self._bounded(ranked)
            self.conn.execute('DELETE FROM memory_summary_items WHERE session_id=?', (session_id,))
            for item in items:
                self.conn.execute('INSERT INTO memory_summary_items(session_id,source_message_id) VALUES (?,?)',
                                  (session_id, item['message_id']))
            return self.read(session_id)

    def forget_source(self, session_id: str, message_id: int) -> None:
        """Erase a selected user source, including any linked versioned facts."""
        if type(message_id) is not int or message_id <= 0:
            raise ValueError('positive message ID required')
        with self.memory.transaction():
            row = self.conn.execute(
                'SELECT m.id FROM memory_messages m JOIN memory_summary_items i ON i.source_message_id=m.id '
                "WHERE m.id=? AND m.session_id=? AND i.session_id=m.session_id AND m.role='user'",
                (message_id, session_id)).fetchone()
            if row is None:
                raise ValueError('selected summary source does not exist in this session')
            linked = self.conn.execute('SELECT DISTINCT fragment_id FROM memory_sources WHERE source_message_id=?',
                                       (message_id,)).fetchall()
            for fact in linked:
                self.memory.forget(fact['fragment_id'])
            self.conn.execute("UPDATE memory_messages SET content='[redacted]' WHERE id=?", (message_id,))
            self.conn.execute("UPDATE memory_sources SET evidence='[redacted]' WHERE source_message_id=?", (message_id,))
            self.memory._invalidate_context()
