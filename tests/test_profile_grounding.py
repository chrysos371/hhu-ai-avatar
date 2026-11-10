import json
from pathlib import Path

import pytest

from avatar.brain.profile_grounding import lookup_profile, review_profile_reply
from avatar.cancellation import CancellationToken, Cancelled
from avatar.main import Avatar


SPEC = json.loads((Path(__file__).resolve().parents[1] /
    'evals/interaction/cycle-02/profile-grounding-protocol.json').read_text())


@pytest.mark.parametrize('case', SPEC['positive_fixtures'])
def test_preregistered_positive_scope(case):
    reply, action = lookup_profile(case['input'], case['profile'])
    if reply is None:
        reply, action = review_profile_reply(case['input'], case['reply'], case['profile'])
    assert action == case['route']
    assert all(item in reply for item in case['expected'])
    assert '也爱游泳' not in reply


@pytest.mark.parametrize('case', SPEC['negative_fixtures'])
def test_preregistered_negative_scope_is_untouched(case):
    assert lookup_profile(case['input'], case['profile']) == (None, None)
    assert review_profile_reply(case['input'], case['reply'], case['profile']) == (case['reply'], None)


class CopyingLLM:
    available = True
    def __init__(self):
        self.generations = 0
    def chat_analysis(self, messages, **kwargs):
        return '{}'
    def chat(self, messages, **kwargs):
        self.generations += 1
        return '我喜欢网球。'
    def stream_chat(self, messages, on_delta=None, **kwargs):
        self.generations += 1
        for piece in ['我喜欢网球。', '我们一起去打吧。']:
            if on_delta:
                on_delta(piece)
        return '我喜欢网球。我们一起去打吧。'


@pytest.fixture
def grounded_avatar():
    model = CopyingLLM()
    avatar = Avatar(db_path=':memory:', llm=model, profile_grounding_enabled=True,
                    summary_enabled=False)
    yield avatar, model
    avatar.memory.close()


def test_lookup_uses_current_name_and_preserves_deletion_provenance(grounded_avatar):
    avatar, model = grounded_avatar
    avatar.respond('我叫陆遥。')
    count = model.generations
    result = avatar.respond('我叫什么名字？')
    assert result['generation_mode'] == 'profile_lookup'
    assert result['profile_grounding']['action'] == 'name_lookup'
    assert '陆遥' in result['reply']
    assert model.generations == count
    fragment = next(row for row in avatar.list_memories() if '陆遥' in row['content'])
    avatar.forget_memory(fragment['id'])
    rows = list(avatar.memory._conn.execute("SELECT content FROM memory_messages WHERE role='assistant'"))
    assert all('陆遥' not in row['content'] for row in rows)
    unknown = avatar.respond('我叫什么名字？')
    assert '陆遥' not in unknown['reply'] and '没有' in unknown['reply']


def test_guard_buffers_and_replaces_whole_reply_before_delta(grounded_avatar):
    avatar, model = grounded_avatar
    deltas = []
    result = avatar.respond('我喜欢网球，请随便聊聊。', cancel=CancellationToken(), on_delta=deltas.append)
    assert result['profile_grounding']['action'] == 'copied_preference'
    assert result['generation_mode'] == 'llm'
    assert result['profile_grounding']['stream_buffered']
    assert deltas == [result['reply']]
    assert '我喜欢网球' not in ''.join(deltas)
    assert '一起去' not in ''.join(deltas)


def test_cancel_after_guarded_delta_never_commits_assistant(grounded_avatar):
    avatar, model = grounded_avatar
    token = CancellationToken()
    with pytest.raises(Cancelled):
        avatar.respond('我喜欢网球，请随便聊聊。', cancel=token, on_delta=lambda text: token.cancel())
    assert avatar.memory._conn.execute("SELECT COUNT(*) FROM memory_messages WHERE role='assistant'").fetchone()[0] == 0


def test_boundary_precedes_lookup_and_copied_preference_review(grounded_avatar):
    avatar, model = grounded_avatar
    result = avatar.respond('你能来我家陪我吗？')
    assert result['boundary']['guarded']
    assert result['profile_grounding']['action'] is None
    assert model.generations == 0


def test_default_keeps_existing_generation_path():
    model = CopyingLLM()
    avatar = Avatar(db_path=':memory:', llm=model, summary_enabled=False)
    try:
        result = avatar.respond('我喜欢网球。')
        assert result['reply'] == '我喜欢网球。'
        assert result['profile_grounding']['enabled'] is False
    finally:
        avatar.memory.close()
