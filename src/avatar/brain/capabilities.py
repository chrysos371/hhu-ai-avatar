"""Runtime facts for ordinary replies, not a model classification or execution API.

Only receipts whose user sources already belong to this reply's privacy lineage
may enter the bounded snapshot. A receipt proves a local commit, not current
reminder state, external delivery, or a human acknowledgement.
"""
from dataclasses import dataclass
import math

from ..cancellation import Cancelled

_ACTIONS = frozenset({'reminder.created', 'reminder.cancelled', 'reminder.completed', 'reminder.claimed_due'})
_TOOLS = frozenset({'get_weather', 'list_reminders', 'read_webpage', 'search_documents', 'web_search'})


@dataclass(frozen=True)
class LocalReceipt:
    id: int
    source_message_id: int
    action: str
    reminder_id: int
    recorded_at: float


@dataclass(frozen=True)
class CapabilitySnapshot:
    revision: int
    source_message_id: int
    scope: str
    turn_tools_allowed: bool
    receipts: tuple[LocalReceipt, ...]
    has_more: bool

    def data(self):
        return {'version': 1, 'branch': 'ordinary_reply',
            'source': {'message_id': self.source_message_id, 'revision': self.revision, 'verified': True},
            'attribution': {'scope': self.scope, 'turn_tools_allowed': self.turn_tools_allowed},
            'external_delivery': {'sms': False, 'email': False, 'phone': False},
            'local_execution': {'scope': 'bounded_existing_reply_sources', 'limit': 20,
                'items': [vars(row).copy() for row in self.receipts], 'has_more': self.has_more,
                'complete_history': False, 'current_reminder_state_verified': False,
                'external_delivery_verified': False, 'human_acknowledgement_verified': False},
            'text_generation_executes_actions': False, 'semantic_verifier': False}


def checked_tool_inventory():
    from ..tools.web_agent import REGISTRY
    if frozenset(REGISTRY.names) != _TOOLS:
        raise ValueError('Runtime tool inventory changed; update the capability contract before use')
    return tuple(sorted(_TOOLS))  # Declaration only; never readiness/execution evidence.


def snapshot(memory, *, session_id, source_message_id, user_text, revision, scope, known_source_ids):
    """Read a single source-bound snapshot without writes or a caller commit."""
    if (type(source_message_id) is not int or not 0 < source_message_id <= 2**63-1
            or type(revision) is not int or not 0 <= revision <= 2**63-1
            or not isinstance(session_id, str) or not session_id
            or not isinstance(user_text, str) or not user_text or user_text == '[redacted]'):
        raise Cancelled('Capability source identity unavailable')
    if (scope.scope not in {'current_user', 'fictional_character', 'unverified'}
            or type(scope.revision) is not int or scope.revision != revision
            or type(scope.allows_actions) is not bool or type(scope.allows_facts) is not bool
            or scope.allows_facts != (scope.scope == 'current_user')
            or scope.allows_actions and not scope.allows_facts):
        raise Cancelled('Capability attribution unavailable')
    if (not isinstance(known_source_ids, (set, frozenset)) or source_message_id not in known_source_ids
            or len(known_source_ids) > 512
            or any(type(n) is not int or not 0 < n <= source_message_id for n in known_source_ids)):
        raise Cancelled('Capability sources are not in the current reply lineage')
    conn = memory._conn
    owned = not conn.in_transaction
    if owned:
        conn.execute('BEGIN')
    try:
        if memory.context_revision != revision:
            raise Cancelled('Capability context changed')
        row = conn.execute('SELECT role,content,session_id FROM memory_messages WHERE id=?',
            (source_message_id,)).fetchone()
        if not row or row['role'] != 'user' or row['content'] != user_text or row['session_id'] != session_id:
            raise Cancelled('Capability source no longer matches current user')
        # Restrict the query itself, rather than reading/copying untracked text.
        rows = conn.execute('''SELECT r.id,r.source_message_id,r.action,r.reminder_id,r.recorded_at
            FROM memory_action_receipts r JOIN memory_messages m ON m.id=r.source_message_id
            AND m.role='user' AND m.session_id=r.session_id AND m.content!='[redacted]'
            WHERE r.session_id=? AND r.context_revision=? AND r.source_message_id IN ('''
            + ','.join('?' for _ in known_source_ids) + ') ORDER BY r.id DESC LIMIT 21',
            [session_id, revision, *sorted(known_source_ids)]).fetchall()
        receipts = []
        for item in reversed(rows[:20]):
            if (any(type(item[k]) is not int or item[k] <= 0 for k in ('id', 'source_message_id', 'reminder_id'))
                    or item['action'] not in _ACTIONS or type(item['recorded_at']) not in (int, float)
                    or not math.isfinite(item['recorded_at'])):
                raise Cancelled('Local capability receipt malformed')
            receipts.append(LocalReceipt(**dict(item)))
        return CapabilitySnapshot(revision, source_message_id, scope.scope, scope.allows_actions,
            tuple(receipts), len(rows) > 20)
    finally:
        if owned:
            conn.rollback()
