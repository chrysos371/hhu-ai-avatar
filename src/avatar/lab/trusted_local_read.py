"""Isolated source-authorized local reads; production factories never install this.

A numbered mention is a bounded parameter basis, not general intent proof.
The conservative exclusions and model routing still require separate evaluation.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import json
import math
import re
import time

from ..brain.facts import _mask_quoted
from ..brain.reminders import CHINA, ReminderStore
from ..brain.speaker_context import SpeakerContextStore
from ..cancellation import Cancelled


_ID = re.compile(
    r'(?:提醒(?:的编号|编号|#)?[ \t]*(?P<before>[0-9]+)'
    r'(?![\dA-Za-z_.+:/-])|编号[ \t]*(?P<after>[0-9]+)'
    r'(?![\dA-Za-z_.+:/-])(?:的)?提醒)')
_EXCLUDED = re.compile(r'改写|代写|写一句|台词|只写|引用|不要|不用|不必|不需|不准|禁止|别查|别读|别执行')
_POLICY = ('本机提醒依赖程序运行并处理到期事项；网页接收还需要页面在线并轮询。'
           '服务退出期间无法自动投递，记录保存不等于已经送达。'
           '当前没有短信、邮件或电话提醒通道；客户端确认也不证明你已阅读。')


def visible_source(text):
    """Mask quote and bounded Markdown code spans; unclosed code masks the tail."""
    masked = list(_mask_quoted(text))
    raw = ''.join(masked)
    cursor = 0
    while cursor < len(raw):
        opening = re.search(r'`+|~{3,}', raw[cursor:])
        if opening is None:
            break
        start = cursor + opening.start()
        token = opening.group()
        after = cursor + opening.end()
        character = re.escape(token[0])
        closing = re.search(r'(?<!' + character + ')' + re.escape(token) + r'(?!' + character + ')', raw[after:])
        end = len(raw) if closing is None else after + closing.end()
        masked[start:end] = ' ' * (end - start)
        cursor = end
    return ''.join(masked)


def parameter_basis(text, arguments, tool):
    """Validate only this finite lab source/parameter contract, never execute."""
    if not isinstance(arguments, dict):
        return 'invalid_arguments'
    if tool == 'read_reminder_delivery_policy':
        if arguments:
            return 'unexpected_arguments'
    elif tool == 'read_reminder_state':
        if set(arguments) != {'reminder_id'}:
            return 'unexpected_arguments'
        ident = arguments['reminder_id']
        if type(ident) is not int or not 0 < ident <= 2**63 - 1:
            return 'invalid_reminder_id'
    else:
        return 'unknown_read_tool'
    visible = visible_source(text)
    if '提醒' not in visible:
        return 'local_reminder_domain_not_explicit'
    if _EXCLUDED.search(visible):
        return 'read_intent_excluded'
    if tool == 'read_reminder_state':
        matches = list(_ID.finditer(visible))
        if len(matches) != 1:
            return 'unbound_reminder_id'
        digits = matches[0]['before'] or matches[0]['after']
        if (len(digits) > 19 or not 0 < int(digits) <= 2**63 - 1
                or int(digits) != ident
                or matches[0].end() < len(visible) and visible[matches[0].end()].isdigit()):
            return 'unbound_reminder_id'
    return None


_ERRORS = {
    'invalid_arguments': '工具参数必须为JSON对象。',
    'unexpected_arguments': '工具字段不符合当前只读契约，不能附加权限或来源字段。',
    'invalid_reminder_id': '提醒编号必须为有效的正整数，不能使用布尔、小数或字符串。',
    'unknown_read_tool': '这不是当前允许的本地只读工具。',
    'local_reminder_domain_not_explicit': '当前未引用原文没有明确本地提醒领域。',
    'read_intent_excluded': '当前原文触发写作、引用或否定读取的保守排除规则。',
    'unbound_reminder_id': '当前原文没有唯一、明确且与参数相符的提醒编号，不得猜测编号。',
    'stored_state_unavailable': '记录存在，但状态暂时无法可靠读取。',
}


@dataclass(frozen=True)
class _Turn:
    ident: int
    text: str
    session_id: str
    revision: int
    scope: str
    allowed: bool
    speaker_row: tuple


@dataclass(frozen=True)
class ReadResult:
    ok: bool
    data: dict | None
    error: dict | None
    reply: str
    source_message_id: int
    revision: int
    observed_at: float


class LabReadSession:
    """Own a trusted current-source binding outside Avatar's ordinary due claim."""

    def __init__(self, memory, session_id, *, checkpoint=None):
        if not isinstance(session_id, str) or not session_id:
            raise ValueError('a real lab session identifier is required')
        if memory._conn.in_transaction:
            raise Cancelled('lab startup requires released caller transaction')
        self.memory = memory
        self.reminders = ReminderStore(memory)  # startup schema, before any read
        self.speaker = SpeakerContextStore(memory)
        self.session_id = session_id
        self._checkpoint = checkpoint or (lambda: None)
        self._turn = None
        self._last_result = None

    def begin_turn(self, text):
        self._checkpoint()
        if not isinstance(text, str) or not 0 < len(text) <= 2000:
            raise ValueError('bounded nonempty user text required')
        if self.memory._conn.in_transaction:
            raise Cancelled('source entry requires its own committed transaction')
        revision = self.memory.context_revision
        with self.memory.transaction():
            ident = self.memory.add_message('user', text, self.session_id)
            scope = self.speaker.observe(text, revision, ident)
            basis = self.memory._conn.execute('SELECT * FROM memory_web_speaker_state WHERE id=1').fetchone()
        self._turn = _Turn(ident, text, self.session_id, revision, scope.scope,
                           scope.allows_actions is True, tuple(basis))
        self._last_result = None
        return ident

    @contextmanager
    def _snapshot(self):
        conn = self.memory._conn
        owned = not conn.in_transaction
        if owned:
            conn.execute('BEGIN')
        try:
            yield conn
        finally:
            if owned:
                conn.rollback()

    def _authorize(self, conn):
        turn = self._turn
        if turn is None or turn.scope != 'current_user' or not turn.allowed:
            raise Cancelled('current independent real source authority unavailable')
        source = conn.execute('SELECT role,content,session_id FROM memory_messages WHERE id=?',
                              (turn.ident,)).fetchone()
        latest = conn.execute("SELECT COALESCE(MAX(id),0) FROM memory_messages WHERE role='user'").fetchone()[0]
        speaker = conn.execute('SELECT * FROM memory_web_speaker_state WHERE id=1').fetchone()
        if (self.memory.context_revision != turn.revision or not source or source['role'] != 'user'
                or source['content'] != turn.text or source['content'] == '[redacted]'
                or source['session_id'] != turn.session_id or latest != turn.ident
                or not speaker or tuple(speaker) != turn.speaker_row):
            raise Cancelled('current source, speaker or revision changed')
        restored = self.speaker._restore(turn.revision, turn.ident + 1)
        if restored.scope != 'current_user' or not restored.allows_actions:
            raise Cancelled('stored source basis cannot authorize this turn')

    def ensure_current(self):
        self._checkpoint()
        with self._snapshot() as conn:
            self._authorize(conn)

    def execute(self, tool, arguments):
        self._checkpoint()
        with self._snapshot() as conn:
            self._authorize(conn)
            turn = self._turn
            code = parameter_basis(turn.text, arguments, tool)
            data = None
            if code:
                reply = '这次没有可靠读取提醒信息。' + _ERRORS[code]
            elif tool == 'read_reminder_delivery_policy':
                data = {'requires_running_server': True, 'web_requires_active_client_polling': True,
                        'external_delivery_channels': [], 'human_reading_verified': False}
                reply = _POLICY
            else:
                row = conn.execute("""SELECT r.id,r.title,r.due_at,r.status,r.notified_at,
                    d.acknowledged_at AS client_ack FROM memory_reminders r
                    LEFT JOIN memory_reminder_deliveries d ON d.reminder_id=r.id WHERE r.id=?""",
                    (arguments['reminder_id'],)).fetchone()
                data = {'id': arguments['reminder_id'], 'exists': row is not None,
                        'state': None, 'human_reading_verified': False}
                if row is None:
                    reply = f'未找到编号{arguments["reminder_id"]}的提醒记录。'
                else:
                    labels = {'active': '有效', 'cancelled': '已取消', 'completed': '已完成'}
                    try:
                        if (not isinstance(row['title'], str) or row['status'] not in labels
                                or type(row['due_at']) not in (int, float) or not math.isfinite(row['due_at'])):
                            raise ValueError('invalid stored state')
                        due = datetime.fromtimestamp(row['due_at'], CHINA).strftime('%Y-%m-%d %H:%M')
                        data['state'] = {'title': row['title'], 'status': row['status'],
                            'due_at': row['due_at'], 'service_claim_recorded': row['notified_at'] is not None,
                            'client_ack_recorded': row['client_ack'] is not None}
                        title = json.dumps(row['title'], ensure_ascii=False)
                        ack = '已记录客户端确认，但不证明已阅读。' if row['client_ack'] is not None else '尚无客户端确认记录。'
                        reply = (f'编号{row["id"]}，标题{title}：记录状态为{labels[row["status"]]}，'
                                 f'提醒时间为{due}（北京时间）。' + ack + _POLICY)
                    except (ValueError, OverflowError, OSError):
                        code = 'stored_state_unavailable'
                        reply = _ERRORS[code]
            result = ReadResult(code is None, data, {'code': code, 'message': _ERRORS[code]} if code else None,
                                reply, turn.ident, turn.revision, time.time())
        # A caller-owned snapshot is preserved for execute, but cannot publish
        # until released; ensure_current outside that old snapshot is mandatory.
        self.ensure_current()
        self._last_result = result
        return result

    def publish(self, result):
        self._checkpoint()
        if self.memory._conn.in_transaction:
            raise Cancelled('publication requires released caller transaction')
        self.ensure_current()
        if result is not self._last_result:
            raise Cancelled('result is not the latest issued read for this source')
        return result.reply
