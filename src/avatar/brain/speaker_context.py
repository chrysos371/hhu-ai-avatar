"""Persist bounded source IDs for pure speaker parsing, never model/tool replay."""
import json

from .speaker_scope import SpeakerScope


class SpeakerContextStore:
    def __init__(self, memory):
        self.memory, self.conn = memory, memory._conn

    @staticmethod
    def _unknown(revision):
        scope = SpeakerScope(); scope.clear(revision); scope.scope = 'unverified'
        scope.allows_actions = False
        return scope

    def _restore(self, revision, current_id):
        row = self.conn.execute('SELECT * FROM memory_web_speaker_state WHERE id=1').fetchone()
        if row is None:
            if self.conn.execute("SELECT 1 FROM memory_messages WHERE role='user' AND id<? LIMIT 1", (current_id,)).fetchone():
                return self._unknown(revision)
            scope = SpeakerScope(); scope.clear(revision); return scope
        try:
            if (row['format_version'] != 1 or row['context_revision'] != revision
                    or type(row['cursor']) is not int or not 0 <= row['cursor'] < current_id
                    or row['scope'] not in ('current_user', 'fictional_character', 'unverified')):
                return self._unknown(revision)
            # A CLI/other writer may append user speech without this web control
            # state. Do not silently skip an untracked declaration or exit.
            if self.conn.execute("SELECT 1 FROM memory_messages WHERE role='user' AND id>? AND id<? LIMIT 1",
                                 (row['cursor'], current_id)).fetchone():
                return self._unknown(revision)
            ids = json.loads(row['source_ids_json'])
            if (not isinstance(ids, list) or len(ids) > 4
                    or any(type(ident) is not int or not 0 < ident <= row['cursor'] for ident in ids)
                    or ids != sorted(set(ids))):
                return self._unknown(revision)
            scope = SpeakerScope(); scope.clear(revision)
            if row['scope'] == 'unverified':
                if ids: return self._unknown(revision)
                return self._unknown(revision)
            for ident in ids:
                source = self.conn.execute('SELECT role,content FROM memory_messages WHERE id=?', (ident,)).fetchone()
                if not source or source['role'] != 'user' or source['content'] == '[redacted]':
                    return self._unknown(revision)
                scope.observe(source['content'], revision, source_id=ident)
            if scope.scope != row['scope'] or scope.source_ids != ids:
                return self._unknown(revision)
            return scope
        except (TypeError, ValueError):
            return self._unknown(revision)

    def observe(self, text, revision, source_id):
        # Caller owns the transaction that inserts this exact user source.
        if not self.conn.in_transaction:
            raise RuntimeError('speaker observation requires source transaction')
        if self.memory.context_revision != revision:
            from ..cancellation import Cancelled
            raise Cancelled('speaker source version changed')
        source = self.conn.execute('SELECT role,content FROM memory_messages WHERE id=?', (source_id,)).fetchone()
        if not source or source['role'] != 'user' or source['content'] != text:
            raise ValueError('speaker source does not match current user message')
        scope = self._restore(revision, source_id)
        scope.observe(text, revision, source_id=source_id)
        self.conn.execute('INSERT OR REPLACE INTO memory_web_speaker_state '
                          '(id,format_version,context_revision,cursor,scope,source_ids_json) VALUES (1,1,?,?,?,?)',
                          (revision, source_id, scope.scope, json.dumps(scope.source_ids)))
        return scope
