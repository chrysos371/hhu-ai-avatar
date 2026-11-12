"""Automatic affect follows privacy revisions, including reentrant mutation."""
import pytest
from contextlib import closing

from avatar.brain.emotion import EmotionEngine
from avatar.brain.memory import MemoryStore
from avatar.cancellation import CancellationToken, Cancelled
from avatar.main import Avatar


class Offline:
    available = False


@pytest.fixture
def avatar(tmp_path):
    instance = Avatar(db_path=str(tmp_path / 'revision.db'), llm=Offline(), summary_enabled=False)
    instance.emotion = EmotionEngine(clock=lambda: 0)
    yield instance
    instance.memory.close()


def prepare(avatar):
    avatar.respond('我很难过')
    assert avatar.emotion.state.arousal == -.2
    return avatar.memory.remember_user('名字', '待纠正资料', source_message_id=avatar._current_message_id)


@pytest.mark.parametrize('operation', ['forget', 'correct'])
def test_public_mutation_immediately_clears_automatic_state(avatar, operation):
    fragment = prepare(avatar)
    if operation == 'forget':
        avatar.forget_memory(fragment)
    else:
        avatar.correct_memory(fragment, '新资料')
    assert avatar.emotion.context_revision == avatar.memory.context_revision
    assert avatar.emotion.state.valence == avatar.emotion.state.arousal == 0
    assert avatar.emotion.user_state.valence == avatar.emotion.user_state.arousal == 0
    assert avatar.emotion._observation_text == '' and avatar.emotion.energy == .5
    assert avatar._turn_context_revision == 0  # Cannot reauthorize old facts.


@pytest.mark.parametrize('operation', ['forget', 'correct'])
@pytest.mark.parametrize('text', ['这是中性请求。', '回到现实'])
def test_external_mutation_is_checked_before_analysis_and_rules(avatar, operation, text):
    fragment = prepare(avatar)
    with closing(MemoryStore(avatar.memory.db_path)) as writer:
        if operation == 'forget':
            writer.forget(fragment)
        else:
            writer.correct(fragment, '新资料')
    result = avatar.respond(text)
    assert result['valence'] == result['arousal'] == 0
    assert result['user_valence'] == result['user_arousal'] == 0
    assert avatar.emotion.context_revision == 1


def test_ordinary_turn_keeps_valid_role_state(avatar):
    prepare(avatar)
    result = avatar.respond('这是中性请求。')
    assert result['valence'] == .05 and result['arousal'] == -.2
    assert result['user_valence'] == result['user_arousal'] == 0
    assert avatar.emotion.context_revision == 0


def test_cancel_after_completed_observation_keeps_same_revision_affect(avatar, monkeypatch):
    token = CancellationToken()
    def analyze(text):
        avatar.emotion.observe(-.4, .3, text=text)
        token.cancel()
    monkeypatch.setattr(avatar, '_analyze', analyze)
    with pytest.raises(Cancelled):
        avatar.respond('已接收的表达。', cancel=token)
    assert avatar.emotion.context_revision == avatar.memory.context_revision == 0
    assert avatar.emotion.user_state.valence == -.4 and avatar.emotion.state.arousal == -.2


@pytest.mark.parametrize('public', [False, True])
@pytest.mark.parametrize('raise_inside', [False, True])
def test_late_old_observation_after_revision_change_cannot_survive(avatar, monkeypatch, public, raise_inside):
    fragment = prepare(avatar)
    def analyze(text):
        if public:
            avatar.forget_memory(fragment)
        else:
            writer = MemoryStore(avatar.memory.db_path)
            try:
                writer.forget(fragment)
            finally:
                writer.close()
        avatar.emotion.observe(-.4, .3, text=text)
        if raise_inside:
            raise Cancelled('late old analysis')
    monkeypatch.setattr(avatar, '_analyze', analyze)
    with pytest.raises(Cancelled):
        avatar.respond('不能将旧结果绑定新版本。')
    assert avatar._turn_context_revision == 0 and avatar.emotion.context_revision == 1
    assert avatar.emotion.user_state.valence == avatar.emotion.state.arousal == 0
    assert avatar.emotion._observation_text == ''
