"""Source-bound writing control for the opt-in release capability contract.

Stores only IDs, never copied drafts; no tool/action authority. Derived from the
previous isolated control-storage mechanism, with a separate table and parser.
"""
from dataclasses import dataclass
import re

from .facts import _mask_quoted
from .tasks import TaskContract, TaskTracker
from ..cancellation import Cancelled

_DIRECT = re.compile(r'^(?:请|麻烦|能否)?(?:(?:替我|帮我|给我|代我)(?:回复|回信)|原样(?:写出|输出))')
_REWRITE = re.compile(r'^(?:请|麻烦)?(?:把|将).{1,200}(?:改得|改成|改为|润色|改写)')
_FRESH_WRITING = re.compile(
    r'^(?:请(?:你)?|麻烦(?:你)?|帮我|替我|给我|代我|'
    r'(?:能不能|可不可以|能否|可否|可以|能)(?:帮我|替我|给我|你)?).{0,24}(?:写|拟|润色|改写|起草|修改)|'
    r'^(?:给.{1,16})?(?:写|拟|润色|改写|起草|修改)')
_META = re.compile(r'^(?:请|麻烦)?(?:帮我)?(?:解释|分析|讨论|教我|告诉我)')
_WRITING_SUBTASK = re.compile(r'(?:[，,。；;]|并|然后|再)(?:请|帮我|替我|给我)?(?:写|拟|润色|改写|起草|修改)')
_END = re.compile(r'^(?:我们)?(?:先|再)?(?:不写了|先不写|不要写了|不用写了|换个话题|取消写作|回到现实|结束角色扮演)(?=[，,。！!\s]|$)')


def _advance_frame(text, writing):
    """Return (writing, new root); quoted requests never become instructions."""
    clean = _mask_quoted(text).strip()
    if re.match(r'^(?:请)?提醒我', clean):
        return False, False  # A local reminder title is not a writing contract.
    if _END.match(clean): return False, False
    # Mixed end/request clauses are not silently assigned a creative frame.
    if re.search(r'[，,。；;]\s*(?:不写了|不要写了|取消写作|回到现实)', clean):
        return None, False
    if _DIRECT.match(clean): return True, True
    if _REWRITE.match(clean) and _mask_quoted(text) != text:
        return True, True
    if (writing and _REWRITE.match(clean)
            and re.match(r'^(?:请|麻烦)?(?:把|将)(?:它|这(?:句|条|段|封)|上一版|刚才那(?:句|条|段))', clean)):
        return True, False
    if _META.match(clean) and not _WRITING_SUBTASK.search(clean):
        return False, False
    tracker = TaskTracker()
    previous = TaskContract(source='validated-source-pointer') if writing else None
    tracker.current = previous
    tracker.update(text)
    fresh = tracker.current is not None and tracker.current is not previous
    if fresh and not (_FRESH_WRITING.match(clean) or _WRITING_SUBTASK.search(clean)):
        return False, False
    return tracker.current is not None, fresh


@dataclass(frozen=True)
class ResponseFrame:
    frame: str
    root_id: int | None
    cursor: int
    revision: int
    parsed_sources: int
    reason: str | None = None

    def metadata(self): return vars(self).copy()


class ResponseFrames:
    LIMIT = 64

    def root_text(self, frame):
        if frame.frame != 'writing':
            return ''
        if self.memory.context_revision != frame.revision:
            raise Cancelled('writing root context changed')
        state = self.conn.execute('SELECT * FROM memory_response_frames WHERE id=1').fetchone()
        source = self.conn.execute('SELECT role,content FROM memory_messages WHERE id=?', (frame.root_id,)).fetchone()
        if (not state or state['cursor'] != frame.cursor or state['context_revision'] != frame.revision
                or state['frame'] != 'writing' or state['root_id'] != frame.root_id
                or not source or source['role'] != 'user' or source['content'] == '[redacted]'
                or _advance_frame(source['content'], False)[0] is not True):
            raise Cancelled('writing root no longer matches source-bound control')
        return source['content']

    def __init__(self, memory):
        self.memory, self.conn = memory, memory._conn
        with memory.transaction():
            self.conn.execute('CREATE TABLE IF NOT EXISTS memory_response_frames '
                '(id INTEGER PRIMARY KEY CHECK(id=1),format_version INTEGER NOT NULL,'
                'context_revision INTEGER NOT NULL,cursor INTEGER NOT NULL,frame TEXT NOT NULL,root_id INTEGER)')
            cursor = self.conn.execute("SELECT COALESCE(MAX(id),0) FROM memory_messages WHERE role='user'").fetchone()[0]
            # Existing history before installation is never replayed to invent a
            # missing frame. A fresh installation starts from a known empty state.
            self.conn.execute('INSERT OR IGNORE INTO memory_response_frames VALUES (1,1,?,?,?,NULL)',
                (memory.context_revision, cursor, 'unverified' if cursor else 'ordinary'))

    def observe(self, text, revision, source_id, *, session_id):
        with self.memory.transaction():
            if self.memory.context_revision != revision:
                raise Cancelled('composition source version changed')
            current = self.conn.execute('SELECT role,content,session_id FROM memory_messages WHERE id=?', (source_id,)).fetchone()
            if not current or current['role'] != 'user' or current['content'] != text or current['session_id'] != session_id or text == '[redacted]':
                raise Cancelled('composition source does not match current user')
            row = self.conn.execute('SELECT * FROM memory_response_frames WHERE id=1').fetchone()
            frame, root, cursor, reason = 'unverified', None, source_id-1, 'state_invalid'
            if row is not None:
                if type(row['cursor']) is int and row['cursor'] >= source_id:
                    # Concurrent older completions must not roll control back.
                    return ResponseFrame('unverified', None, source_id, revision, 0, 'state_ahead')
                valid = (row['format_version'] == 1 and row['context_revision'] == revision
                    and type(row['cursor']) is int and 0 <= row['cursor'] < source_id
                    and row['frame'] in ('ordinary', 'writing', 'unverified'))
                if valid:
                    frame, root, cursor, reason = row['frame'], row['root_id'], row['cursor'], None
                    if frame == 'writing':
                        anchor = self.conn.execute('SELECT role,content FROM memory_messages WHERE id=?', (root,)).fetchone() if type(root) is int and 0 < root <= cursor else None
                        if (not anchor or anchor['role'] != 'user' or anchor['content'] == '[redacted]'
                                or _advance_frame(anchor['content'], False)[0] is not True):
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
                writing, fresh = _advance_frame(source['content'], frame == 'writing')
                if writing is True:
                    if fresh: root = source['id']
                    frame = 'writing'
                elif writing is None:
                    frame, root, reason = 'unverified', None, 'mixed_frame'
                elif frame != 'unverified' or _END.match(_mask_quoted(source['content']).strip()):
                    frame, root = 'ordinary', None
            self.conn.execute('INSERT OR REPLACE INTO memory_response_frames VALUES (1,1,?,?,?,?)',
                (revision, source_id, frame, root))
            return ResponseFrame(frame, root, source_id, revision, len(pending), reason)
