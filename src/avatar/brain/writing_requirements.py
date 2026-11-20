"""Bounded, source-backed writing requirements; not semantic task verification.

SQLite stores pointers only. Values are compiled from actual user messages in
the current privacy epoch; assistant drafts never become control instructions.
"""
from dataclasses import dataclass
import json
import re

from .reminder_query_targets import visible_source
from ..cancellation import Cancelled

_POLISH = re.compile(r'(?:请)?(?:再)?(?:短一点|简短一点|自然一点|口语一点|礼貌一点|正式一点)[。！!]?')
_SIGNATURE = re.compile(r'署名(?:请)?(?:用|改成|改为|写成|为)')
_SIGNATURE_VALUE = r'\s*(【[^【】\n]{1,40}】|“[^“”\n]{1,40}”|「[^「」\n]{1,40}」|[^，,。；;\n？！!?\s]{1,40})'
_RELEASE = re.compile(r'(?:不要|不用|无需|去掉|删除)署名')
_SENTENCES = re.compile(r'(?:压缩到|控制在|改成|改为|写成|写)([一二两三四五六七八九十1-9]|10)句(?:话)?')
_BODY = re.compile(r'只(?:给|要|输出|回复|交付)(?:正文|稿件正文)')
_NUMBERS = dict(zip('一二三四五六七八九十', range(1, 11)), 两=2)
_ROLES = r'老师|导师|室友|同学|朋友|同事|班长|房东|姐姐|妹妹|哥哥|弟弟'
_SOURCE_LIMIT = 32


def author_role(sources):
    role = None
    for _, text in sources:
        clean = re.sub(r'【[^【】\n]*】', lambda m: ' ' * len(m.group()), visible_source(text))
        direct = re.search(r'(?:写|拟|起草)(' + _ROLES + r')(?:的)?(?:回复|回信)', clean)
        addressed = re.search(r'(?:发|发送|寄)(?:了)?给(' + _ROLES + r')', clean)
        if direct:
            role = direct.group(1)
        elif addressed and re.search(r'(?:写|拟|起草)(?:对方|他|她)(?:的)?回复', clean):
            role = addressed.group(1)
        if re.search(r'改(?:成|为|用)我(?:自己)?的?(?:口吻|第一人称)', clean):
            role = '用户'
    return role


def _compile_sources(sources):
    signature, count, body, omitted, seen = None, None, False, False, []
    for _, text in sources:
        clean = visible_source(text)
        # Placeholders and quoted/code values are data, even when they contain
        # command-looking strings. Offsets stay aligned with the original.
        clean = re.sub(r'【[^【】\n]*】', lambda m: ' ' * len(m.group()), clean)
        for clause in re.finditer(r'[^，,。；;\n]+', clean):
            instruction = clause.group()
            if re.search(r'[？?]|(?:吗|么|呢)\s*$', instruction):
                continue
            if _RELEASE.search(instruction):
                signature = None
                omitted = True
            for match in _SIGNATURE.finditer(instruction):
                offset = clause.start() + match.end()
                value = re.match(_SIGNATURE_VALUE, text[offset:])
                if value:
                    signature = value.group(1)
                    omitted = False
                    seen.append(signature)
            found = _SENTENCES.search(instruction)
            if found:
                digits = found.group(1)
                count = int(digits) if digits.isascii() else _NUMBERS[digits]
            if _BODY.search(instruction):
                body = True
    return signature, count, body, omitted, tuple(dict.fromkeys(seen)) if omitted else ()


def compile_sources(sources):
    return _compile_sources(sources)[:3]


def standalone_edit(text):
    """Finite bare controls may continue an existing, independently valid root."""
    if type(text) is not str or not 0 < len(text) <= 2000:
        return False
    clean = re.sub(r'【[^【】\n]*】', lambda m: ' ' * len(m.group()), visible_source(text))
    clauses = list(re.finditer(r'[^，,。；;\n]+', clean))
    if not clauses:
        return False
    for match in clauses:
        visible = match.group().strip()
        raw = text[match.start():match.end()].strip()
        if re.fullmatch(_SIGNATURE.pattern + _SIGNATURE_VALUE, raw):
            if _compile_sources(((1, raw),))[0] is None:
                return False
        elif not any(pattern.fullmatch(visible) for pattern in (_RELEASE, _SENTENCES, _BODY)):
            return False
    return True


@dataclass(frozen=True)
class WritingRequirements:
    source_verified: bool = False
    signature: str | None = None
    sentence_count: int | None = None
    body_only: bool = False
    source_message_ids: tuple[int, ...] = ()
    reason: str | None = None
    # These private in-memory values are never copied into the metadata table
    # or public result. They fence prompt assembly and final publication.
    state: tuple = ()
    sources: tuple = ()
    signature_omitted: bool = False
    forbidden_signatures: tuple[str, ...] = ()

    @classmethod
    def from_sources(cls, sources, *, state=()):
        """Compile already checked user rows, without granting source authority."""
        sources = tuple(sources)
        if (not 1 <= len(sources) <= _SOURCE_LIMIT
                or any(type(i) is not int or not 0 < i <= 2**63-1 or type(text) is not str
                       or not text.strip() or text == '[redacted]' for i, text in sources)):
            raise ValueError('invalid bounded writing sources')
        ids = tuple(i for i, _ in sources)
        if ids != tuple(sorted(set(ids))):
            raise ValueError('writing sources must be unique and ordered')
        signature, count, body, omitted, forbidden = _compile_sources(sources)
        return cls(True, signature, count, body, ids, None, state, sources,
                   signature_omitted=omitted, forbidden_signatures=forbidden)

    @property
    def author_role(self):
        explicit = author_role(self.sources) if self.source_verified else None
        contract = self.literal_contract
        return explicit or (contract.perspective if contract and contract.perspective else None)

    @property
    def literal_contract(self):
        if not self.source_verified:
            return None
        from .tasks import TaskTracker
        tracker = TaskTracker()
        for index, (_, text) in enumerate(self.sources):
            # ResponseFrames already validated the actual root, including
            # direct reply forms which need no separate old experiment flag.
            tracker.update(text, writing_root=index == 0)
        return tracker.current

    @property
    def verbatim_literal(self):
        if not self.source_verified or len(self.sources) != 1:
            return None
        found = re.fullmatch(r'(?:请)?原样(?:写出|输出)(?:这句话|这句(?:小说)?台词|这段话)?[：:\s]*'
            r'(?:“([^“”\n]{1,120})”|「([^「」\n]{1,120})」|"([^"\n]{1,120})")[。！!]?\s*',
            self.sources[0][1])
        if found:
            value = next(x for x in found.groups() if x is not None)
            contract = self.literal_contract
            if contract is not None and contract.required_literals == [value]:
                return value
        return None

    def data(self):
        contract = self.literal_contract
        return dict(version=1, source_verified=self.source_verified, signature=self.signature,
                    sentence_count=self.sentence_count, body_only=self.body_only,
                    source_message_ids=list(self.source_message_ids), reason=self.reason,
                    signature_omitted=self.signature_omitted, forbidden_signatures=list(self.forbidden_signatures),
                    author_role=self.author_role,
                    verbatim_literal=self.verbatim_literal,
                    required_literals=list(contract.required_literals) if contract else [],
                    forbidden_literals=list(contract.forbidden_literals) if contract else [],
                    semantic_verifier=False)


class WritingRequirementStore:
    LIMIT = _SOURCE_LIMIT

    def __init__(self, memory):
        self.memory, self.conn = memory, memory._conn
        with memory.transaction():
            self.conn.execute('CREATE TABLE IF NOT EXISTS memory_writing_requirements '
                '(id INTEGER PRIMARY KEY CHECK(id=1),format_version INTEGER NOT NULL,'
                'context_revision INTEGER NOT NULL,cursor INTEGER NOT NULL,root_id INTEGER,'
                'status TEXT NOT NULL,source_ids TEXT NOT NULL)')

    def _row(self):
        row = self.conn.execute('SELECT * FROM memory_writing_requirements WHERE id=1').fetchone()
        return tuple(row) if row else ()

    @classmethod
    def _ids(cls, raw, root, cursor):
        if type(root) is not int or type(cursor) is not int or not 0 < root <= cursor:
            return None
        try:
            ids = json.loads(raw)
        except (TypeError, ValueError):
            return None
        if (not isinstance(ids, list) or not 1 <= len(ids) <= cls.LIMIT
                or any(type(i) is not int or not 0 < i <= cursor for i in ids)
                or ids != sorted(set(ids)) or ids[0] != root):
            return None
        return ids

    def observe(self, frame):
        """Called in the same admission transaction as ResponseFrames.observe."""
        with self.memory.transaction():
            if self.memory.context_revision != frame.revision:
                raise Cancelled('writing requirement source version changed')
            previous = self._row()
            if previous and type(previous[3]) is int and previous[3] >= frame.cursor:
                return  # An older concurrent admission cannot replace newer state.
            ids, status = [], 'unverified'
            if frame.frame == 'writing':
                if (previous and previous[1] == 1 and previous[2] == frame.revision
                        and previous[4] == frame.root_id and previous[5] == 'verified'):
                    prior = self._ids(previous[6], frame.root_id, previous[3])
                    if prior is not None:
                        ids = prior
                        pending = self.conn.execute("SELECT id,content FROM memory_messages WHERE role='user' "
                            'AND id>? AND id<=? ORDER BY id LIMIT 65', (previous[3], frame.cursor)).fetchall()
                        if len(pending) <= 64:
                            ids += [r['id'] for r in pending if not _POLISH.fullmatch(r['content'].strip())]
                            status = 'verified'
                elif (not previous or type(previous[3]) is int) and frame.root_id > (previous[3] if previous else 0):
                    pending = self.conn.execute("SELECT id,content FROM memory_messages WHERE role='user' "
                        'AND id>=? AND id<=? ORDER BY id LIMIT 65', (frame.root_id, frame.cursor)).fetchall()
                    if len(pending) <= 64:
                        ids = [r['id'] for r in pending if r['id'] == frame.root_id or not _POLISH.fullmatch(r['content'].strip())]
                        status = 'verified'
                if len(ids) > self.LIMIT:
                    ids, status = [], 'unverified'
            elif frame.frame == 'ordinary':
                status = 'ordinary'
            self.conn.execute('INSERT OR REPLACE INTO memory_writing_requirements VALUES(1,1,?,?,?,?,?)',
                (frame.revision, frame.cursor, frame.root_id, status, json.dumps(ids)))

    def read(self, frame):
        owned = not self.conn.in_transaction
        if owned:
            self.conn.execute('BEGIN')
        try:
            row = self._row()
            actual_frame = self.conn.execute('SELECT context_revision,cursor,frame,root_id '
                'FROM memory_response_frames WHERE id=1').fetchone()
            if (not row or row[1] != 1 or row[2] != frame.revision
                    or self.memory.context_revision != frame.revision or row[3] != frame.cursor
                    or row[4] != frame.root_id or row[5] != 'verified' or frame.frame != 'writing'
                    or not actual_frame or tuple(actual_frame) != (frame.revision, frame.cursor, 'writing', frame.root_id)):
                return WritingRequirements(reason='source_unverified')
            ids = self._ids(row[6], frame.root_id, frame.cursor)
            if ids is None:
                return WritingRequirements(reason='source_ids_invalid')
            sources = []
            for ident in ids:
                source = self.conn.execute('SELECT role,content FROM memory_messages WHERE id=?', (ident,)).fetchone()
                if not source or source['role'] != 'user' or not source['content'] or source['content'] == '[redacted]':
                    return WritingRequirements(reason='source_unavailable')
                sources.append((ident, source['content']))
            return WritingRequirements.from_sources(sources, state=row)
        finally:
            if owned:
                self.conn.rollback()

    def ensure_current(self, requirements, frame):
        if not requirements.source_verified:
            return
        if self.read(frame) != requirements:
            raise Cancelled('writing requirements changed before publication')
