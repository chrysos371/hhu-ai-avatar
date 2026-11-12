"""Real HTTP state reads invalidate automatic affect without deleting overrides."""
from contextlib import closing
from types import SimpleNamespace
import threading

import pytest

from avatar.brain.emotion import EmotionEngine
from avatar.brain.memory import MemoryStore
from avatar.web_state import automatic_emotion_snapshot
from test_web_api_v1 import api_v1


@pytest.mark.parametrize('operation', ['forget', 'correct'])
@pytest.mark.parametrize('first_read', ['/api/v1/emotion', '/api/v1/dashboard', '/api/state'])
def test_all_state_readers_clear_external_revision_even_if_window_is_current(api_v1, operation, first_read):
    request, server = api_v1
    assert request('/api/v1/chat', {'text': '我很难过'})[0] == 200
    before = request('/api/v1/emotion')[1]['data']
    assert before['user_observation']['valence'] < 0 and before['automatic']['arousal'] < 0
    assert before['recent_observations'][0]['context_revision'] == 0
    with closing(MemoryStore(server.db_path)) as writer:
        source = writer._conn.execute("SELECT id FROM memory_messages WHERE role='user'").fetchone()[0]
        fragment = writer.remember_user('名字', '旧资料', source_message_id=source)
        if operation == 'forget':
            writer.forget(fragment)
        else:
            writer.correct(fragment, '新资料')
        server.context_revision = writer.context_revision  # Window already refreshed by finally.
    code, body = request(first_read)
    assert code == 200
    state = body['data'] if first_read.startswith('/api/v1/') else body
    automatic = state.get('automatic', state.get('emotion', state))
    assert automatic['valence'] == automatic['arousal'] == 0
    emotion = request('/api/v1/emotion')[1]['data']
    assert emotion['user_observation'] == {'valence': 0, 'arousal': 0}
    assert emotion['recent_observations'] == []
    dashboard = request('/api/v1/dashboard')[1]['data']
    assert dashboard['recent_events'] == [] and dashboard['energy'] == .5
    result = request('/api/v1/chat', {'text': '这是中性请求。'})[1]['data']
    assert result['valence'] == result['arousal'] == 0
    assert request('/api/v1/emotion')[1]['data']['recent_observations'][0]['context_revision'] == 1


def test_manual_expression_override_and_valid_continuity_remain_independent(api_v1):
    request, server = api_v1
    draft = request('/api/v1/emotion/draft', {'values': {'valence': .4, 'arousal': -.2},
        'duration_seconds': 300, 'reason': '独立人工表达'})[1]['data']
    assert request(f"/api/v1/operations/{draft['draft_id']}/confirm",
        {'confirmation_token': draft['confirmation_token']})[0] == 200
    assert request('/api/v1/chat', {'text': '我很难过'})[0] == 200
    result = request('/api/v1/chat', {'text': '这是中性请求。'})[1]['data']
    state = request('/api/v1/emotion')[1]['data']
    assert state['automatic']['arousal'] < 0 and state['user_observation']['valence'] == 0
    override = state['override']
    with closing(MemoryStore(server.db_path)) as writer:
        fragment = writer.remember_user('名字', '资料', source_message_id=result['conversation']['user_message_id'])
        writer.forget(fragment)
    state = request('/api/v1/emotion')[1]['data']
    assert state['automatic'] == {'valence': 0, 'arousal': 0}
    assert state['override'] == override and state['effective'] == {'valence': .4, 'arousal': -.2}


def test_unknown_stale_and_bool_event_revisions_fail_closed_and_snapshots_are_copies():
    with closing(MemoryStore(':memory:')) as memory:
        engine = EmotionEngine(clock=lambda: 0)
        engine.bind_context_revision(0)
        engine.observe(-.4, .3)
        server = SimpleNamespace(state_lock=threading.RLock(), emotion=engine, chat_events=[
            {'context_revision': 0, 'detail': {'value': 1}}, {'context_revision': True},
            {'context_revision': 1}, {'context_revision': '0'}, {'valence': -.9}])
        snapshot = automatic_emotion_snapshot(server, memory)
        assert snapshot['events'] == [{'context_revision': 0, 'detail': {'value': 1}}]
        assert snapshot['automatic']['arousal'] == -.2
        snapshot['automatic']['arousal'] = 1
        snapshot['events'][0]['detail']['value'] = 9
        assert engine.state.arousal == -.2 and server.chat_events[0]['detail']['value'] == 1
        engine.observe(.8, .4)
        assert snapshot['user_observation']['valence'] == -.4


def test_unbound_engine_state_clears_before_first_api_snapshot():
    with closing(MemoryStore(':memory:')) as memory:
        engine = EmotionEngine(clock=lambda: 0)
        engine.observe(-.4, .3)
        server = SimpleNamespace(state_lock=threading.RLock(), emotion=engine, chat_events=[])
        snapshot = automatic_emotion_snapshot(server, memory)
        assert snapshot['automatic'] == snapshot['user_observation'] == {'valence': 0, 'arousal': 0}
        assert snapshot['energy'] == .5
