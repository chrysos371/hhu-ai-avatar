"""Lab-only bounded control pointers, not copied drafts or model/tool replay."""
from dataclasses import dataclass
import re

from ..brain.facts import _mask_quoted
from ..brain.tasks import TaskContract, TaskTracker
from ..cancellation import Cancelled

_DIRECT = re.compile(r'^(?:请|麻烦|能否)?(?:(?:替我|帮我|给我|代我)(?:回复|回信)|原样(?:写出|输出))')
_END = re.compile(r'^(?:我们)?(?:先|再)?(?:不写了|先不写|不要写了|不用写了|换个话题|取消写作|回到现实|结束角色扮演)(?=[，,。！!\s]|$)')


def advance_frame(text, writing):
    """Return (writing, new root); quoted requests never become instructions."""
    clean = _mask_quoted(text).strip()
    if _END.match(clean): return False, False
    # Mixed end/request clauses are not silently assigned a creative frame.
    if re.search(r'[，,。；;]\s*(?:不写了|不要写了|取消写作|回到现实)', clean):
        return None, False
    if _DIRECT.match(clean): return True, True
    tracker = TaskTracker()
    previous = TaskContract(source='validated-source-pointer') if writing else None
    tracker.current = previous
    tracker.update(text)
    return tracker.current is not None, tracker.current is not None and tracker.current is not previous


@dataclass(frozen=True)
class CompositionFrame:
    frame: str
    root_id: int | None
    cursor: int
    revision: int
    parsed_sources: int
    reason: str | None = None

    def metadata(self): return vars(self).copy()


class CompositionSources:
    LIMIT = 64

    def __init__(self, memory):
        self.memory, self.conn = memory, memory._conn
        with memory.transaction():
            self.conn.execute('CREATE TABLE IF NOT EXISTS lab_body_composition_state '
                '(id INTEGER PRIMARY KEY CHECK(id=1),format_version INTEGER NOT NULL,'
                'context_revision INTEGER NOT NULL,cursor INTEGER NOT NULL,frame TEXT NOT NULL,root_id INTEGER)')
            cursor = self.conn.execute("SELECT COALESCE(MAX(id),0) FROM memory_messages WHERE role='user'").fetchone()[0]
            # Existing history before installation is never replayed to invent a
            # missing frame. A fresh installation starts from a known empty state.
            self.conn.execute('INSERT OR IGNORE INTO lab_body_composition_state VALUES (1,1,?,?,?,NULL)',
                (memory.context_revision, cursor, 'unverified' if cursor else 'ordinary'))

    def observe(self, text, revision, source_id):
        with self.memory.transaction():
            if self.memory.context_revision != revision:
                raise Cancelled('composition source version changed')
            current = self.conn.execute('SELECT role,content FROM memory_messages WHERE id=?', (source_id,)).fetchone()
            if not current or current['role'] != 'user' or current['content'] != text or text == '[redacted]':
                raise Cancelled('composition source does not match current user')
            row = self.conn.execute('SELECT * FROM lab_body_composition_state WHERE id=1').fetchone()
            frame, root, cursor, reason = 'unverified', None, source_id-1, 'state_invalid'
            if row is not None:
                if type(row['cursor']) is int and row['cursor'] >= source_id:
                    # Concurrent older completions must not roll control back.
                    return CompositionFrame('unverified', None, source_id, revision, 0, 'state_ahead')
                valid = (row['format_version'] == 1 and row['context_revision'] == revision
                    and type(row['cursor']) is int and 0 <= row['cursor'] < source_id
                    and row['frame'] in ('ordinary', 'writing', 'unverified'))
                if valid:
                    frame, root, cursor, reason = row['frame'], row['root_id'], row['cursor'], None
                    if frame == 'writing':
                        anchor = self.conn.execute('SELECT role,content FROM memory_messages WHERE id=?', (root,)).fetchone() if type(root) is int and 0 < root <= cursor else None
                        if (not anchor or anchor['role'] != 'user' or anchor['content'] == '[redacted]'
                                or advance_frame(anchor['content'], False)[0] is not True):
                            frame, root, cursor, reason = 'unverified', None, source_id-1, 'root_invalid'
                    elif root is not None:
                        frame, root, cursor, reason = 'unverified', None, source_id-1, 'unexpected_root'
            pending = self.conn.execute("SELECT id,content FROM memory_messages WHERE role='user' AND id>? AND id<=? ORDER BY id LIMIT ?",
                (cursor, source_id, self.LIMIT+1)).fetchall()
            if len(pending) > self.LIMIT:
                frame, root, reason = 'unverified', None, 'pending_limit_exceeded'
                pending = [pending[-1]] if pending[-1]['id'] == source_id else [dict(id=source_id, content=text)]
            for source in pending:
                if source['content'] == '[redacted]':
                    frame, root, reason = 'unverified', None, 'source_redacted'; continue
                writing, fresh = advance_frame(source['content'], frame == 'writing')
                if writing is True:
                    if fresh: root = source['id']
                    frame = 'writing'
                elif writing is None:
                    frame, root, reason = 'unverified', None, 'mixed_frame'
                elif frame != 'unverified' or _END.match(_mask_quoted(source['content']).strip()):
                    frame, root = 'ordinary', None
            self.conn.execute('INSERT OR REPLACE INTO lab_body_composition_state VALUES (1,1,?,?,?,?)',
                (revision, source_id, frame, root))
            return CompositionFrame(frame, root, source_id, revision, len(pending), reason)
