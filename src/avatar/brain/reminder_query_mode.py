"""Actual-source reader for explicitly selected, finite reminder query mode."""
from contextlib import contextmanager
import time

from ..cancellation import Cancelled
from .reminder_queries import QueryReply, QuerySource, ReminderQuery, _render_query
from .reminder_query_targets import derive_read_target
from .speaker_context import SpeakerContextStore

_CONTROL_REPLIES = {
    'clarify_reference': '请明确要查询的提醒编号；当前没有唯一编号，这次未读取提醒记录。',
    'mixed_read_targets': '你同时提到了记录状态和运行、送达条件，请明确本轮要查询哪一种；这次未读取提醒。',
    'query_goal_unspecified': '请明确要查询某个编号的提醒状态，还是了解运行、送达条件；这次未读取提醒。',
    'no_read': '本轮未查询提醒记录。这里仅支持查询具体编号的状态或运行、送达条件，不执行写入或外发。',
}


class ReminderQueryReader:
    """Bind Avatar's existing committed user row, never add or observe a source.

    A reader is private to a single synchronous turn. Each read and subsequent
    publication check verifies the latest user row and the captured durable
    speaker basis. Caller permissions alone cannot authorize this service.
    """

    def __init__(self, store, text, source, *, checkpoint=None):
        if store.conn.in_transaction:
            raise Cancelled('query mode requires a released source transaction')
        if (type(source) is not QuerySource
                or type(source.source_message_id) is not int or not 0 < source.source_message_id <= 2**63-1
                or type(source.revision) is not int or not 0 <= source.revision <= 2**63-1
                or not isinstance(source.session_id, str) or not source.session_id
                or source.scope != 'current_user' or source.turn_tools_allowed is not True):
            raise Cancelled('independent current-user query source required')
        # Validate before reading any business data, including control-only turns.
        derive_read_target(text)
        self.store, self.text, self.source = store, text, source
        self.checkpoint = checkpoint or (lambda: None)
        self.speaker = SpeakerContextStore(store.memory)
        self._speaker_row = None
        with self._snapshot() as conn:
            row = conn.execute('SELECT * FROM memory_web_speaker_state WHERE id=1').fetchone()
            if row is None:
                raise Cancelled('durable speaker basis unavailable')
            self._speaker_row = tuple(row)
            self._authorize(conn)

    @contextmanager
    def _snapshot(self):
        conn = self.store.conn
        owned = not conn.in_transaction
        if owned:
            conn.execute('BEGIN')
        try:
            yield conn
        finally:
            if owned:
                conn.rollback()

    def _authorize(self, conn):
        source = self.source
        row = conn.execute('SELECT role,content,session_id FROM memory_messages WHERE id=?',
                           (source.source_message_id,)).fetchone()
        latest = conn.execute("SELECT COALESCE(MAX(id),0) FROM memory_messages WHERE role='user'").fetchone()[0]
        speaker = conn.execute('SELECT * FROM memory_web_speaker_state WHERE id=1').fetchone()
        if (self.store.memory.context_revision != source.revision or not row or row['role'] != 'user'
                or row['content'] != self.text or row['content'] == '[redacted]'
                or row['session_id'] != source.session_id or latest != source.source_message_id
                or not speaker or tuple(speaker) != self._speaker_row):
            raise Cancelled('query source or speaker basis changed')
        restored = self.speaker._restore(source.revision, source.source_message_id + 1)
        if restored.scope != 'current_user' or not restored.allows_actions:
            raise Cancelled('query source is not independently authorized')
        # A mixed role exit may persist current_user for the NEXT turn. Recheck
        # this actual text rather than retroactively granting its old request.
        restored.observe(self.text, source.revision, source_id=source.source_message_id)
        if restored.scope != 'current_user' or not restored.allows_actions:
            raise Cancelled('mixed source cannot authorize this query')

    def ensure_current(self):
        self.checkpoint()
        with self._snapshot() as conn:
            self._authorize(conn)

    def resolve(self):
        self.checkpoint()
        with self._snapshot() as conn:
            self._authorize(conn)
            target = derive_read_target(self.text)
            if target.route in ('read_state', 'read_policy'):
                command = (ReminderQuery('status', target.arguments['reminder_id'])
                           if target.route == 'read_state' else ReminderQuery('conditions'))
                result = _render_query(conn, command, self.source)
                reply, metadata = result.reply, result.metadata
            else:
                key = target.reason if target.route == 'clarify_intent' else target.route
                reply = _CONTROL_REPLIES[key]
                metadata = {'source_message_id': self.source.source_message_id,
                    'revision': self.source.revision, 'observed_at': time.time(),
                    'business_mutations': False, 'human_reading_verified': False,
                    'state': None, 'exists': None, 'reminder_id': None}
            metadata.update(version=2, mode='reminder_query', route=target.route,
                reason=target.reason, arguments=target.arguments, evidence=target.evidence,
                session_id=self.source.session_id, model_calls=0,
                semantic_intent_verified=False, business_data_read=target.route == 'read_state')
            self.checkpoint()
        self.ensure_current()
        return QueryReply(reply, metadata)
