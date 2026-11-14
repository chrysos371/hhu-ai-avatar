"""Isolated typed historical evidence experiment; production never activates it.

Keep the production source gate and untrusted original reply. Finite observation
fields are added only when their metadata agrees with the published reply. This
does not query live state or turn a read/ACK into human or remote-send evidence.
"""
from contextlib import contextmanager
from datetime import datetime
import json
import math

from ..brain import query_history
from ..brain.reminders import CHINA
from ..brain.reminder_query_mode import _CONTROL_REPLIES
from .history_representation import _PRODUCTION_FORMATTER

ARMS = frozenset({'verified_snapshot_history', 'typed_observation_history'})
FIELDS = frozenset({'observed_record_state', 'current_record_state',
    'observation_source_message_id', 'client_ack_in_observation',
    'mail_sms_phone_sent', 'human_reading_verified',
    'human_task_completion_verified', 'user_name_from_title'})
STATES = frozenset({'active', 'cancelled', 'completed', 'missing', 'unknown'})
_LABELS = {'active': '有效', 'cancelled': '已取消', 'completed': '已完成'}
_POLICY = ('本机提醒依赖程序运行并处理到期事项；网页接收还需要页面在线并轮询。'
    '服务退出期间无法自动投递，记录保存不等于已经送达。'
    '当前没有短信、邮件或电话提醒通道；客户端确认也不证明你已阅读。')
_active_token = None


def _positive_id(value):
    return type(value) is int and 0 < value <= 2**63-1


def _observation(reply, metadata):
    """Validate representation consistency, not arbitrary caller authority.

    The production formatter and its SDK/Web caller still own authorization.
    Unknown/inconsistent fields fall back to the unchanged production envelope.
    No title or arbitrary user prose enters the finite projection.
    """
    route = metadata['route']
    if metadata.get('human_reading_verified') is not False:
        raise ValueError('unsupported human evidence')
    if route != 'read_state':
        if any(metadata.get(k) is not None for k in ('state', 'exists', 'reminder_id')):
            raise ValueError('non-state query contains record state')
        if route == 'read_policy':
            expected = _POLICY
        else:
            key = metadata['reason'] if route == 'clarify_intent' else route
            expected = _CONTROL_REPLIES[key]
        if reply != expected:
            raise ValueError('control reply mismatch')
        return None
    ident = metadata.get('reminder_id')
    if not _positive_id(ident) or ident != metadata['arguments']['reminder_id']:
        raise ValueError('observation record identity mismatch')
    exists = metadata.get('exists'); state = metadata.get('state')
    if exists is False and state is None:
        if reply != f'未找到编号{ident}的提醒记录。':
            raise ValueError('missing reply mismatch')
        status, claimed, acknowledged = 'missing', False, False
    elif exists is True and type(state) is dict:
        if (not _positive_id(state.get('id')) or state['id'] != ident
                or type(state.get('status')) is not str or state['status'] not in _LABELS
                or type(state.get('title')) is not str or not 0 < len(state['title']) <= 2000
                or type(state.get('service_claim_recorded')) is not bool
                or type(state.get('client_ack_recorded')) is not bool):
            raise ValueError('invalid finite observation shape')
        due = state.get('due_at')
        # Check range before isfinite: a huge integer must not overflow to float.
        if type(due) not in (int, float) or not 0 < due <= 253402300799 or not math.isfinite(due):
            raise ValueError('invalid observation date')
        formatted = datetime.fromtimestamp(due, CHINA).strftime('%Y-%m-%d %H:%M')
        acknowledged = state['client_ack_recorded']; claimed = state['service_claim_recorded']
        ack = '已记录客户端确认，但不代表已阅读。' if acknowledged else '尚无客户端确认记录。'
        expected = (f'编号{ident}「{state["title"]}」：记录状态为{_LABELS[state["status"]]}，'
            f'提醒时间为{formatted}（北京时间）。'+ack+'提醒需程序运行并处理到期事项，网页接收需在线轮询。')
        if reply != expected:
            raise ValueError('state and published reply disagree')
        status = state['status']
    else:
        raise ValueError('observation unavailable')
    return {'reminder_id': ident, 'status_at_observation': status,
        'service_claim_recorded': claimed, 'client_ack_recorded': acknowledged,
        'source_message_id': metadata['source_message_id'], 'observed_at': metadata['observed_at']}


def typed_query_history_content(reply, metadata, **source):
    original = _PRODUCTION_FORMATTER(reply, metadata, **source)
    if original is None:
        return None
    try:
        observation = _observation(reply, metadata)
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        return original
    prefix, body = original.split('\n', 1)
    payload = json.loads(body)
    payload['typed_historical_evidence'] = {
        'version': 1, 'query_operation': metadata['route'],
        'record_observation': observation,
        'live_record_state_verified': False,
        'query_proves_mail_sms_phone_sent': False,
        'query_proves_human_reading': False,
        'query_proves_human_task_completion': False,
    }
    return prefix+'\n'+json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False)


@contextmanager
def typed_history_representation(arm):
    """Explicit serial lab override, with ownership and exception restoration."""
    global _active_token
    if type(arm) is not str or arm not in ARMS:
        raise ValueError('unknown typed history arm')
    if _active_token is not None or query_history.query_history_content is not _PRODUCTION_FORMATTER:
        raise RuntimeError('history formatter already owned or modified')
    token = object()
    def formatter(reply, metadata, **source):
        if arm == 'typed_observation_history':
            return typed_query_history_content(reply, metadata, **source)
        return _PRODUCTION_FORMATTER(reply, metadata, **source)
    _active_token = token; query_history.query_history_content = formatter
    try:
        yield
    finally:
        owned = _active_token is token and query_history.query_history_content is formatter
        query_history.query_history_content = _PRODUCTION_FORMATTER; _active_token = None
        if not owned:
            raise RuntimeError('typed formatter changed during isolated trial')


def _valid_shape(value):
    if type(value) is not dict or set(value) != FIELDS:
        return False
    if any(type(value[k]) is not str or value[k] not in STATES
           for k in ('observed_record_state', 'current_record_state')):
        return False
    if any(type(value[k]) is not bool for k in ('mail_sms_phone_sent',
           'human_reading_verified', 'human_task_completion_verified')):
        return False
    source = value['observation_source_message_id']
    if source is not None and not _positive_id(source):
        return False
    ack = value['client_ack_in_observation']
    if ack is not None and type(ack) is not bool:
        return False
    name = value['user_name_from_title']
    return name is None or type(name) is str and 0 < len(name) <= 80


def parse_typed_history_answer(reply):
    if not isinstance(reply, str) or not 0 < len(reply) <= 16000:
        return None
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value: raise ValueError('duplicate key')
            value[key] = item
        return value
    def nonfinite(value):
        raise ValueError('nonfinite constant')
    try:
        value = json.loads(reply, object_pairs_hook=unique, parse_constant=nonfinite)
        return value if _valid_shape(value) else None
    except (ValueError, TypeError, RecursionError):
        return None


def score_typed_history_answer(reply, expected):
    if not _valid_shape(expected): raise ValueError('invalid registered typed answer')
    parsed = parse_typed_history_answer(reply)
    checks = {key: parsed is not None and parsed[key] == expected[key] for key in sorted(FIELDS)}
    return {'format_valid': parsed is not None, 'parsed': parsed,
        'field_checks': checks, 'task_correct': all(checks.values()),
        'general_semantic_verified': False}
