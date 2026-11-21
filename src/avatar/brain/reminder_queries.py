"""Explicit, source-authorized reminder reads; never claim, ACK or invoke a model.

Chat message logging is owned by Avatar. This module reads reminder business
state at one snapshot; a client ACK is not a human read receipt.
"""
from dataclasses import dataclass
from datetime import datetime
import json
import math
import re
import time

from ..cancellation import Cancelled
from .reminders import CHINA


_PREFIX = r'(?:请)?(?:查询|查看)提醒'
_CONDITIONS = re.compile(_PREFIX + r'(?:运行|送达)条件[。！？!?]?')
_STATUS = re.compile(_PREFIX + r'(?:编号|#)?[ \t]*([0-9]{1,19})(?:号)?(?:状态)?[。！？!?]?')
_NATURAL_STATUS = re.compile(r'(?:请)?提醒(?:编号|#)[ \t]*([0-9]{1,19})'
    r'(?:现在)?(?:是什么状态|状态是什么|还有效吗|取消了吗|完成了吗)[。！？!?]?')
_NATURAL_POLICY = re.compile(r'(?:程序|服务)(?:退出|关闭|停止|关机)后提醒'
    r'(?:还)?(?:能|会)(?:发短信|发邮件|打电话)吗[。！？!?]?')
_NATURAL_REFERENCE = re.compile(r'(?:这条|那条)提醒(?:现在)?(?:真的存在吗|还存在吗)[。！？!?]?')
_NATURAL_SHUTDOWN = re.compile(r'如果我把(?:程序|服务)(?:关掉|关闭|停止)[，,]还会自动收到提醒吗[。！？!?]?')


@dataclass(frozen=True)
class ReminderQuery:
    kind: str
    reminder_id: int | None = None


@dataclass(frozen=True)
class QuerySource:
    source_message_id: int
    session_id: str
    revision: int
    scope: str
    turn_tools_allowed: bool


@dataclass(frozen=True)
class QueryReply:
    reply: str
    metadata: dict


def parse_query(text, *, allow_natural=False):
    if type(allow_natural) is not bool:
        raise ValueError('allow_natural must be a boolean')
    if not isinstance(text, str):
        return None
    clean = text.strip()
    if allow_natural and (_NATURAL_STATUS.fullmatch(clean) or _NATURAL_POLICY.fullmatch(clean)
                          or _NATURAL_REFERENCE.fullmatch(clean) or _NATURAL_SHUTDOWN.fullmatch(clean)):
        from .reminder_query_targets import derive_read_target
        target = derive_read_target(text)
        if target.route == 'read_state':
            return ReminderQuery('status', target.arguments['reminder_id'])
        if target.route == 'read_policy':
            return ReminderQuery('conditions')
        if target.route == 'clarify_reference' and _NATURAL_REFERENCE.fullmatch(clean):
            return ReminderQuery('reference')
    from .reminder_query_targets import explicit_list_query
    if explicit_list_query(text):
        return ReminderQuery('list')
    # Preserve the existing explicit WebAgent list alias; this service handles
    # numbered reads/conditions, not the old list tool's dispatch.
    if clean == '查看提醒':
        return None
    if not re.match(_PREFIX, clean):
        return None
    if _CONDITIONS.fullmatch(clean):
        return ReminderQuery('conditions')
    match = _STATUS.fullmatch(clean)
    if match and 0 < int(match[1]) <= 2**63 - 1:
        return ReminderQuery('status', int(match[1]))
    return ReminderQuery('invalid')


def resolve_query(store, command, text, context, *, checkpoint=None, allow_natural=False):
    """Read under caller's snapshot or a private read transaction; no commits.

    The caller must recheck its response epoch after this transaction releases,
    before publishing. This snapshot does not guarantee future immutable state.
    """
    if (type(command) is not ReminderQuery or command != parse_query(text, allow_natural=allow_natural)
            or command.reminder_id is not None and type(command.reminder_id) is not int):
        raise Cancelled('reminder query does not match current source text')
    if (type(context.source_message_id) is not int or not 0 < context.source_message_id <= 2**63 - 1
            or type(context.revision) is not int or not 0 <= context.revision <= 2**63 - 1
            or not isinstance(context.session_id, str) or not context.session_id
            or context.scope != 'current_user' or context.turn_tools_allowed is not True):
        raise Cancelled('reminder query source authority is unavailable')
    if checkpoint:
        checkpoint()
    conn = store.conn
    owned = not conn.in_transaction
    if owned:
        conn.execute('BEGIN')
    try:
        source = conn.execute('SELECT role,content,session_id FROM memory_messages WHERE id=?',
                              (context.source_message_id,)).fetchone()
        if (store.memory.context_revision != context.revision or not source or source['role'] != 'user'
                or source['content'] != text or source['content'] == '[redacted]'
                or source['session_id'] != context.session_id):
            raise Cancelled('reminder query source or revision changed')
        result = _render_query(conn, command, context)
        if command.kind in ('status', 'conditions', 'list', 'reference'):
            from .reminder_query_targets import derive_read_target
            target = derive_read_target(text)
            expected = {'status': 'read_state', 'conditions': 'read_policy', 'list': 'read_list',
                        'reference': 'clarify_reference'}[command.kind]
            if target.route != expected:
                raise Cancelled('automatic query has no matching historical source representation')
            result.metadata.update(version=2, mode='reminder_query', route=target.route,
                reason=target.reason, arguments=target.arguments, evidence=target.evidence,
                session_id=context.session_id, model_calls=0, semantic_intent_verified=False,
                business_data_read=target.route in ('read_state', 'read_list'))
        if checkpoint:
            checkpoint()
        return result
    finally:
        if owned:
            conn.rollback()


def _render_query(conn, command, context):
    """Render one already-authorized read in the caller's SQLite snapshot."""
    metadata = {'version': 1, 'kind': command.kind, 'source_message_id': context.source_message_id,
        'revision': context.revision, 'observed_at': time.time(), 'business_mutations': False,
        'reminder_id': command.reminder_id, 'exists': None, 'state': None,
        'requires_running_server': True, 'web_requires_active_client_polling': True,
        'external_delivery_channels': [], 'human_reading_verified': False}
    if command.kind == 'invalid':
        reply = '请使用“查询提醒编号1”或“查看提醒送达条件”。提醒编号须为有效的正整数，且一条消息只包含一个查询。'
    elif command.kind == 'reference':
        from .reminder_query_mode import _CONTROL_REPLIES
        reply = _CONTROL_REPLIES['clarify_reference']
    elif command.kind == 'conditions':
        reply = ('本机提醒依赖程序运行并处理到期事项；网页接收还需要页面在线并轮询。'
            '服务退出期间无法自动投递，记录保存不等于已经送达。'
            '当前没有短信、邮件或电话提醒通道；客户端确认也不证明你已阅读。')
    elif command.kind == 'list':
        count = conn.execute('SELECT COUNT(*) FROM memory_reminders').fetchone()[0]
        rows = conn.execute('SELECT id,title,due_at,status FROM memory_reminders ORDER BY id LIMIT 20').fetchall()
        metadata.update(record_count=count, has_more=count > 20, list_limit=20, records=[])
        try:
            lines = []
            labels = {'active': '有效', 'cancelled': '已取消', 'completed': '已完成'}
            for row in rows:
                if (not isinstance(row['title'], str) or len(row['title']) > 500
                        or row['status'] not in labels or type(row['due_at']) not in (int, float)
                        or not math.isfinite(row['due_at'])):
                    raise ValueError('invalid stored reminder list record')
                due = datetime.fromtimestamp(row['due_at'], CHINA).strftime('%Y-%m-%d %H:%M')
                metadata['records'].append(dict(row))
                title = json.dumps(row['title'], ensure_ascii=False)
                lines.append(f'编号{row["id"]}：{title}，{due}（北京时间），{labels[row["status"]]}。')
            reply = (f'当前本机共有{count}条提醒记录（包含已取消、已完成记录）。'
                + ('以下仅列前20条；其余请在提醒管理页查看。' if count > 20 else '')
                + ('\n'+'\n'.join(lines) if lines else '')
                + '\n这些是本机记录，不代表外部送达或已阅读；到期显示仍依赖程序运行和轮询。')
        except (ValueError, OverflowError, OSError):
            metadata.update(records=[], state_error='stored_reminder_list_unavailable')
            reply = '提醒列表存在暂时无法可靠读取的记录，请在提醒管理页检查；这不表示没有提醒。'
    else:
        row = conn.execute('''SELECT r.id,r.title,r.due_at,r.status,r.notified_at,
            d.acknowledged_at AS client_ack FROM memory_reminders r
            LEFT JOIN memory_reminder_deliveries d ON d.reminder_id=r.id WHERE r.id=?''',
            (command.reminder_id,)).fetchone()
        metadata['exists'] = row is not None
        if row is None:
            reply = f'未找到编号{command.reminder_id}的提醒记录。'
        else:
            try:
                labels = {'active': '有效', 'cancelled': '已取消', 'completed': '已完成'}
                if (not isinstance(row['title'], str) or row['status'] not in labels
                        or type(row['due_at']) not in (int, float) or not math.isfinite(row['due_at'])):
                    raise ValueError('invalid stored reminder state')
                due = datetime.fromtimestamp(row['due_at'], CHINA).strftime('%Y-%m-%d %H:%M')
                metadata['state'] = {'id': row['id'], 'title': row['title'], 'due_at': row['due_at'],
                    'status': row['status'], 'service_claim_recorded': row['notified_at'] is not None,
                    'client_ack_recorded': row['client_ack'] is not None}
                ack = '已记录客户端确认，但不代表已阅读。' if row['client_ack'] is not None else '尚无客户端确认记录。'
                reply = (f'编号{row["id"]}「{row["title"]}」：记录状态为{labels[row["status"]]}，提醒时间为{due}（北京时间）。'
                    + ack + '提醒需程序运行并处理到期事项，网页接收需在线轮询。')
            except (ValueError, OverflowError, OSError):
                metadata['state_error'] = 'stored_reminder_state_unavailable'
                reply = '这条提醒的状态暂时无法可靠读取，请在提醒管理页检查记录。'
    return QueryReply(reply, metadata)
