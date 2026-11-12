"""State metadata tags the automatic snapshot, including an external-write race."""
from contextlib import closing

import pytest

from avatar.brain.emotion import EmotionEngine
from avatar.brain.memory import MemoryStore
from test_web_api_v1 import api_v1


@pytest.mark.parametrize('page', ['emotion', 'dashboard'])
@pytest.mark.parametrize('operation', ['forget', 'correct'])
def test_state_context_tracks_instance_and_privacy_version(api_v1, page, operation):
    request, server = api_v1
    result = request('/api/v1/chat', {'text': '我很难过'})[1]['data']
    before = request('/api/v1/' + page)[1]['data']
    assert before['context'] == {'instance_id': server.session_id, 'revision': 0}
    with closing(MemoryStore(server.db_path)) as writer:
        fragment = writer.remember('受控状态来源', source_message_id=result['conversation']['user_message_id'])
        if operation == 'forget':
            writer.forget(fragment)
        else:
            writer.correct(fragment, '纠正后资料')
    after = request('/api/v1/' + page)[1]['data']
    assert after['context'] == {'instance_id': server.session_id, 'revision': 1}
    automatic = after.get('automatic', after.get('emotion'))
    assert automatic['valence'] == automatic['arousal'] == 0


@pytest.mark.parametrize('page', ['emotion', 'dashboard'])
def test_write_during_snapshot_cannot_retag_old_automatic_values_with_new_revision(api_v1, page):
    request, server = api_v1
    result = request('/api/v1/chat', {'text': '已完成的来源'})[1]['data']
    with closing(MemoryStore(server.db_path)) as writer:
        fragment = writer.remember('受控状态来源', source_message_id=result['conversation']['user_message_id'])

    class MutatingEmotion(EmotionEngine):
        on_read = None

        @property
        def state(self):
            if self.on_read is not None:
                callback, self.on_read = self.on_read, None
                callback()
            return super().state

    def forget():
        with closing(MemoryStore(server.db_path)) as writer:
            writer.forget(fragment)

    engine = MutatingEmotion(clock=lambda: 0)
    engine.bind_context_revision(0)
    engine.observe(-.4, .3)
    engine.on_read = forget
    server.emotion = engine
    raced = request('/api/v1/' + page)[1]['data']
    assert raced['context'] == {'instance_id': server.session_id, 'revision': 0}
    automatic = raced.get('automatic', raced.get('emotion'))
    assert automatic['arousal'] == -.2
    with closing(MemoryStore(server.db_path)) as reader:
        assert reader.context_revision == 1
    fresh = request('/api/v1/' + page)[1]['data']
    assert fresh['context'] == {'instance_id': server.session_id, 'revision': 1}
    automatic = fresh.get('automatic', fresh.get('emotion'))
    assert automatic['valence'] == automatic['arousal'] == 0
