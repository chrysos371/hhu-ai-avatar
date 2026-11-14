"""Minimal historical observation experiment, preserving the failed C48 control.

The producer/source/privacy boundary remains the production caller's. Added
observation values have a corresponding published reply; unused claim flags and
query-proves-action/human statements are not projected into this representation.
"""
from contextlib import contextmanager
import json

from ..brain import query_history
from .history_representation import _PRODUCTION_FORMATTER
from .typed_history_observation import _observation, typed_query_history_content

ARMS = frozenset({'production_snapshot','C48_typed_control','minimal_observation'})
_active_token = None


def minimal_query_history_content(reply,metadata,**source):
    original = _PRODUCTION_FORMATTER(reply,metadata,**source)
    if original is None:
        return None
    try:
        observation = _observation(reply,metadata)
    except (KeyError,TypeError,ValueError,OverflowError,OSError):
        return original
    if observation is None:
        minimal = {'version':1,'kind':'not_observed','reminder_id':None,
            'source_message_id':None,'status_at_observation':None,'client_ack_recorded':None}
    else:
        minimal = {'version':1,
            'kind':'observed_missing' if observation['status_at_observation']=='missing' else 'observed_record',
            'reminder_id':observation['reminder_id'],'source_message_id':observation['source_message_id'],
            'status_at_observation':observation['status_at_observation'],
            'client_ack_recorded':observation['client_ack_recorded']}
    prefix,body = original.split('\n',1); payload = json.loads(body)
    payload['minimal_historical_observation'] = minimal
    return prefix+'\n'+json.dumps(payload,ensure_ascii=False,sort_keys=True,allow_nan=False)


@contextmanager
def observation_representation(arm):
    """Serial research activation only, never installed by production factories."""
    global _active_token
    if type(arm) is not str or arm not in ARMS:
        raise ValueError('unknown minimal history arm')
    if _active_token is not None or query_history.query_history_content is not _PRODUCTION_FORMATTER:
        raise RuntimeError('history formatter already owned or modified')
    token = object()
    def formatter(reply,metadata,**source):
        if arm == 'minimal_observation':
            return minimal_query_history_content(reply,metadata,**source)
        if arm == 'C48_typed_control':
            return typed_query_history_content(reply,metadata,**source)
        return _PRODUCTION_FORMATTER(reply,metadata,**source)
    _active_token = token; query_history.query_history_content = formatter
    try:
        yield
    finally:
        owned = _active_token is token and query_history.query_history_content is formatter
        query_history.query_history_content = _PRODUCTION_FORMATTER; _active_token = None
        if not owned:
            raise RuntimeError('minimal history formatter changed during isolated trial')
