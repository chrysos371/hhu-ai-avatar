"""Read a bounded, source-verified suffix of completed Web conversation pairs.

The caller holds the current user-source transaction after speaker observation.
This reader copies past role/content only: it performs no model call or action.
"""
from dataclasses import dataclass
import json

from ..cancellation import Cancelled


@dataclass(frozen=True)
class ContextMessage:
    role: str
    content: str
    message_id: int


@dataclass(frozen=True)
class ContextWindow:
    messages: tuple[ContextMessage, ...]
    revision: int

    @property
    def source_ids(self) -> tuple[int, ...]:
        return tuple(message.message_id for message in self.messages)


def _decode(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate conversation result key')
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError('non-finite conversation result value')

    return json.loads(text, object_pairs_hook=unique, parse_constant=nonfinite)


def _valid_text(value):
    return isinstance(value, str) and bool(value.strip())


class ConversationContextStore:
    def __init__(self, memory):
        self.memory = memory
        self.conn = memory._conn

    def _dependencies_valid(self, assistant_id, user_id):
        dependencies = self.conn.execute(
            "SELECT c.source_type,c.source_id,m.id AS message_id, "
            "m.content AS message_content,f.id AS fragment_id,f.content AS fragment_content "
            "FROM memory_response_context c "
            "LEFT JOIN memory_messages m ON c.source_type='message' AND m.id=c.source_id "
            "LEFT JOIN memory_fragments f ON c.source_type='fragment' AND f.id=c.source_id "
            "WHERE c.message_id=?", (assistant_id,),
        ).fetchall()
        own_source = False
        for dependency in dependencies:
            identifier = dependency['source_id']
            if type(identifier) is not int or identifier <= 0:
                return False
            if dependency['source_type'] == 'message':
                content = dependency['message_content']
                if (dependency['message_id'] is None or identifier >= assistant_id
                        or not _valid_text(content) or content == '[redacted]'):
                    return False
                own_source = own_source or identifier == user_id
            elif dependency['source_type'] == 'fragment':
                # Superseded facts can be valid historical context; missing or
                # malformed content cannot support a derived reply.
                if dependency['fragment_id'] is None or not _valid_text(dependency['fragment_content']):
                    return False
            else:
                return False
        return own_source

    def _result(self, assistant, user, scope, revision):
        if (assistant['role'] != 'assistant' or user['role'] != 'user'
                or not _valid_text(assistant['content']) or not _valid_text(user['content'])
                or assistant['content'] == '[redacted]' or user['content'] == '[redacted]'
                or assistant['context_tracked'] != 1
                or assistant['result_revision'] != revision
                or not assistant['result_json']
                or assistant['session_id'] != user['session_id']):
            return None
        try:
            result = _decode(assistant['result_json'])
        except (ValueError, TypeError):
            return None
        if not isinstance(result, dict):
            return None
        source = result.get('conversation')
        attribution = result.get('speaker_attribution')
        if (not isinstance(source, dict) or not isinstance(attribution, dict)
                or attribution.get('scope') != scope
                or result.get('reply') != assistant['content']
                or result.get('generation_mode') not in {
                    'llm', 'rules', 'rules_speaker_control', 'rules_speaker_scope', 'rules_reminder_query'}
                or type(source.get('revision')) is not int or source['revision'] != revision
                or type(source.get('user_message_id')) is not int
                or source['user_message_id'] != user['id']
                or type(source.get('assistant_message_id')) is not int
                or source['assistant_message_id'] != assistant['id']
                or source.get('session_id') != user['session_id']):
            return None
        if not self._dependencies_valid(assistant['id'], user['id']):
            return None
        if result['generation_mode'] == 'rules_reminder_query':
            from .query_history import query_history_content
            content = query_history_content(result['reply'], result.get('reminder_query'),
                text=user['content'], source_message_id=user['id'], session_id=user['session_id'],
                revision=revision, scope=attribution.get('scope'),
                turn_tools_allowed=attribution.get('turn_tools_allowed'))
            if content is None:
                return None
            # Private decoded object only: never persist this envelope or trust
            # a same-named key injected into an ordinary non-query result.
            result['_query_history_context'] = content
        return result

    def read(self, *, current_user_id, scope, expected_revision, limit_messages=18):
        if not self.conn.in_transaction:
            raise RuntimeError('conversation recovery requires current source transaction')
        if (type(current_user_id) is not int or current_user_id <= 0
                or type(expected_revision) is not int or expected_revision < 0
                or type(limit_messages) is not int or not 0 <= limit_messages <= 200):
            raise ValueError('invalid bounded conversation source parameters')
        if self.memory.context_revision != expected_revision:
            raise Cancelled('context changed before conversation recovery')
        current = self.conn.execute(
            'SELECT id,role FROM memory_messages ORDER BY id DESC LIMIT 1'
        ).fetchone()
        if current is None or current['id'] != current_user_id or current['role'] != 'user':
            raise ValueError('conversation recovery requires the current user source')
        empty = ContextWindow((), expected_revision)
        state = self.conn.execute(
            'SELECT format_version,context_revision,cursor,scope '
            'FROM memory_web_speaker_state WHERE id=1'
        ).fetchone()
        if (scope not in ('current_user', 'fictional_character') or state is None
                or state['format_version'] != 1 or state['context_revision'] != expected_revision
                or state['cursor'] != current_user_id or state['scope'] != scope):
            return empty
        bound = limit_messages // 2 * 2
        if bound == 0:
            return empty
        rows = self.conn.execute(
            'SELECT m.id,m.role,m.content,m.session_id,m.context_tracked, '
            'r.context_revision AS result_revision,r.result_json FROM memory_messages m '
            'LEFT JOIN memory_chat_results r ON r.message_id=m.id '
            'WHERE m.id<? ORDER BY m.id DESC LIMIT ?',
            (current_user_id, bound),
        ).fetchall()
        pairs = []
        for index in range(0, len(rows) - 1, 2):
            assistant, user = rows[index], rows[index + 1]
            result = self._result(assistant, user, scope, expected_revision)
            if result is None:
                break
            if result['generation_mode'] == 'rules_reminder_query':
                assistant = dict(assistant)
                assistant['content'] = result['_query_history_context']
            pairs.append((user, assistant))
            if result['generation_mode'] == 'rules_speaker_control':
                break
        messages = tuple(
            ContextMessage(row['role'], row['content'], row['id'])
            for pair in reversed(pairs) for row in pair
        )
        return ContextWindow(messages, expected_revision)
