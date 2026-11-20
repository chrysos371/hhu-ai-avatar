"""One completed, revision-bound role snapshot, without copied private text.

Source hashes detect stale/corrupt references, not a malicious database owner.
Read-only restoration never commits a caller's transaction or replays cognition.
"""
from hashlib import sha256
import json
import math
from time import time


def digest(text):
    return sha256(text.encode('utf-8')).hexdigest()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def decode(text):
    def unique(pairs):
        data = {}
        for key, value in pairs:
            if key in data:
                raise ValueError('duplicate role snapshot key')
            data[key] = value
        return data
    return json.loads(text, object_pairs_hook=unique, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite snapshot')))


class RoleStateStore:
    LIMIT = 512

    def __init__(self, memory, *, wallclock=time):
        self.memory, self.conn, self.wallclock = memory, memory._conn, wallclock
        with memory.transaction():
            self.conn.execute('CREATE TABLE IF NOT EXISTS memory_role_state '
                '(id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL, payload_sha256 TEXT NOT NULL)')

    def _pair(self, source):
        if (type(source) is not dict or set(source) != {
                'session_id', 'revision', 'user_message_id', 'assistant_message_id'}
                or any(type(source[k]) is not int or not 0 < source[k] <= 2**63-1
                       for k in ('user_message_id', 'assistant_message_id'))
                or source['user_message_id'] >= source['assistant_message_id']
                or type(source['revision']) is not int or source['revision'] < 0
                or source['revision'] != self.memory.context_revision
                or type(source['session_id']) is not str or not source['session_id']):
            return False
        rows = self.conn.execute('SELECT id,role,content,session_id,context_tracked '
            'FROM memory_messages ORDER BY id DESC LIMIT 2').fetchall()
        return bool(len(rows) == 2 and rows[0]['id'] == source['assistant_message_id']
            and rows[1]['id'] == source['user_message_id']
            and rows[0]['role'] == 'assistant' and rows[1]['role'] == 'user'
            and rows[0]['context_tracked'] == 1
            and all(r['session_id'] == source['session_id'] and type(r['content']) is str
                    and r['content'].strip() and r['content'] != '[redacted]' for r in rows))

    def _sources(self, source):
        pairs = {('message', source['user_message_id']), ('message', source['assistant_message_id'])}
        pairs.update((r['source_type'], r['source_id']) for r in self.conn.execute(
            'SELECT source_type,source_id FROM memory_response_context WHERE message_id=?',
            (source['assistant_message_id'],)))
        if not 2 <= len(pairs) <= self.LIMIT:
            return None
        result = []
        for kind, identifier in sorted(pairs):
            if kind not in ('message', 'fragment') or type(identifier) is not int or identifier <= 0:
                return None
            if kind == 'message' and identifier > source['assistant_message_id']:
                return None
            table = 'memory_messages' if kind == 'message' else 'memory_fragments'
            row = self.conn.execute('SELECT content FROM ' + table + ' WHERE id=?', (identifier,)).fetchone()
            if row is None or type(row[0]) is not str or not row[0].strip() or row[0] == '[redacted]':
                return None
            result.append(dict(kind=kind, id=identifier, sha256=digest(row[0])))
        return result

    def save(self, engine, *, source, scope, checkpoint=lambda: None):
        """Only called after the complete response path, inside a write batch."""
        with self.memory.transaction():
            checkpoint()
            if not self._pair(source) or engine.context_revision != source['revision']:
                return False
            sources = self._sources(source)
            now = self.wallclock()
            if sources is None or type(now) not in (int, float) or not 0 < now <= 253402300799 or not math.isfinite(now):
                return False
            value = dict(version=1, source=source, scope=scope, saved_at=now,
                         role=engine.role_snapshot(), sources=sources)
            # Validate policy/numbers without changing the live observation.
            from .emotion import EmotionEngine
            validator = EmotionEngine(decay=engine.decay, half_life_seconds=engine.half_life_seconds)
            validator.restore_role_snapshot(value['role'], elapsed=0, revision=source['revision'])
            payload = encode(value)
            self.conn.execute('INSERT OR REPLACE INTO memory_role_state VALUES (1,?,?)', (payload, digest(payload)))
            checkpoint()
            return True

    def restore(self, engine, *, scope='current_user'):
        owned = not self.conn.in_transaction
        if owned:
            self.conn.execute('BEGIN')
        try:
            row = self.conn.execute('SELECT payload,payload_sha256 FROM memory_role_state WHERE id=1').fetchone()
            if row is None or type(row[0]) is not str or len(row[0]) > 150000 or digest(row[0]) != row[1]:
                return False
            data = decode(row[0])
            if (type(data) is not dict or set(data) != {'version','source','scope','saved_at','role','sources'}
                    or type(data['version']) is not int or data['version'] != 1
                    or scope != 'current_user' or data['scope'] != scope or not self._pair(data['source'])):
                return False
            if encode(data['sources']) != encode(self._sources(data['source'])):
                return False
            now, saved = self.wallclock(), data['saved_at']
            if (any(type(x) not in (int, float) or not 0 < x <= 253402300799 or not math.isfinite(x)
                    for x in (now, saved)) or saved > now):
                return False
            engine.restore_role_snapshot(data['role'], elapsed=now-saved, revision=data['source']['revision'])
            return True
        except (ValueError, TypeError, KeyError, OverflowError):
            return False
        finally:
            if owned:
                self.conn.rollback()
