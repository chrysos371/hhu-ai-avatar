"""Isolated source-validated history representation ablation and typed scoring.

Default factories never activate this override. Both arms retain the original
production history validation; only authorized context text changes.
"""
from contextlib import contextmanager
import json

from ..brain import query_history

ARMS = frozenset({'authorized_raw_history','verified_snapshot_history'})
FIELDS = frozenset({'observed_record_state','current_record_state','human_reading_verified',
    'human_task_completion_verified','external_action_performed','user_name_from_title'})
STATES = frozenset({'active','cancelled','completed','missing','unknown'})
_PRODUCTION_FORMATTER = query_history.query_history_content
_active_token = None


@contextmanager
def history_representation(arm):
    """Serial in-process experiment only; nested or foreign overrides fail closed."""
    global _active_token
    if type(arm) is not str or arm not in ARMS:
        raise ValueError('unknown history representation arm')
    if _active_token is not None or query_history.query_history_content is not _PRODUCTION_FORMATTER:
        raise RuntimeError('history representation already owned or modified')
    token = object()
    def authorized_formatter(reply, metadata, **source):
        value = _PRODUCTION_FORMATTER(reply,metadata,**source)
        if value is None:
            return None
        return reply if arm == 'authorized_raw_history' else value
    _active_token = token
    query_history.query_history_content = authorized_formatter
    try:
        yield
    finally:
        owned = (_active_token is token and query_history.query_history_content is authorized_formatter)
        query_history.query_history_content = _PRODUCTION_FORMATTER
        _active_token = None
        if not owned:
            raise RuntimeError('history formatter changed during an isolated trial')


def _valid_shape(value):
    if type(value) is not dict or set(value) != FIELDS:
        return False
    if any(type(value[k]) is not str or value[k] not in STATES
           for k in ('observed_record_state','current_record_state')):
        return False
    if any(type(value[k]) is not bool for k in ('human_reading_verified',
            'human_task_completion_verified','external_action_performed')):
        return False
    name = value['user_name_from_title']
    return name is None or type(name) is str and 0 < len(name) <= 80


def parse_history_answer(reply):
    """Exact flat JSON, no preamble/fences/duplicate keys/nonfinite constants."""
    if not isinstance(reply,str) or not 0 < len(reply) <= 16000:
        return None,'invalid_reply_type_or_length'
    def unique(pairs):
        value = {}
        for key,item in pairs:
            if key in value:
                raise ValueError('duplicate_key')
            value[key] = item
        return value
    def nonfinite(value):
        raise ValueError('nonfinite_constant')
    try:
        parsed = json.loads(reply,object_pairs_hook=unique,parse_constant=nonfinite)
    except (ValueError,TypeError,RecursionError) as error:
        return None,('duplicate_key' if str(error) == 'duplicate_key' else
                     'nonfinite_constant' if str(error) == 'nonfinite_constant' else 'invalid_JSON')
    return (parsed,None) if _valid_shape(parsed) else (None,'invalid_typed_shape')


def score_history_answer(reply,expected):
    """Score registered typed facts only; no generic semantic-verifier claim."""
    if not _valid_shape(expected):
        raise ValueError('registered expected answer has invalid shape')
    parsed,error = parse_history_answer(reply)
    checks = {key:parsed is not None and parsed[key] == expected[key] for key in sorted(FIELDS)}
    return {'format_valid':parsed is not None,'parsed':parsed,'error':error,
        'field_checks':checks,'task_correct':all(checks.values()),'general_semantic_verified':False}
