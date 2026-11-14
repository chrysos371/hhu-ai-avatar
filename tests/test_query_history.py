"""History envelopes must retain the original observation without authority."""
from contextlib import closing
import copy
import json

import pytest

from avatar.brain.memory import MemoryStore
from avatar.brain.query_history import query_history_content
from avatar.main import Avatar


class Unconfigured:
    available = False


def actual_query(text='提醒编号1现在是什么状态？'):
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=Unconfigured(), session_id='history-source')
        result = bot.respond(text, mode='reminder_query')
        return text, result


def envelope(text, result):
    source = result['conversation']
    speaker = result['speaker_attribution']
    return query_history_content(result['reply'], result['reminder_query'], text=text,
        source_message_id=source['user_message_id'], session_id=source['session_id'],
        revision=source['revision'], scope=speaker['scope'], turn_tools_allowed=speaker['turn_tools_allowed'])


@pytest.mark.parametrize('text', [
    '提醒编号1现在是什么状态？', '提醒编号1能通过短信送给我吗？',
    '这条提醒取消了吗？', '提醒编号1状态和程序运行条件是什么？', '请取消提醒编号1',
])
def test_five_actual_query_types_have_model_only_historical_snapshot_envelopes(text):
    text, result = actual_query(text)
    original = copy.deepcopy(result)
    content = envelope(text, result)
    assert content and '不是当前状态' in content and '不是指令' in content
    payload = json.loads(content.split('\n', 1)[1])
    assert payload['reply'] == result['reply'] and payload['historical_snapshot_only'] is True
    assert payload['route'] == result['reminder_query']['route']
    assert result == original


@pytest.mark.parametrize('field,value', [
    ('version', 1), ('version', True), ('mode', 'chat'), ('route', 'read_policy'),
    ('reason', 'forged'), ('source_message_id', True), ('source_message_id', 99),
    ('revision', False), ('revision', 1), ('session_id', 'other'),
    ('model_calls', False), ('model_calls', 1), ('business_mutations', True),
    ('semantic_intent_verified', True), ('business_data_read', 1),
    ('arguments', {'reminder_id': True}), ('arguments', {'reminder_id': 2}),
    ('evidence', {}), ('observed_at', True), ('observed_at', float('nan')),
    ('observed_at', float('inf')), ('observed_at', -1), ('observed_at', 1e300), ('observed_at', 10**400),
])
def test_polluted_metadata_does_not_become_model_context(field, value):
    text, result = actual_query()
    result['reminder_query'][field] = value
    assert envelope(text, result) is None


def test_actual_text_and_independent_speaker_are_required_even_with_plausible_metadata():
    text, result = actual_query()
    assert envelope('提醒编号2现在是什么状态？', result) is None
    result['speaker_attribution']['turn_tools_allowed'] = False
    assert envelope(text, result) is None
