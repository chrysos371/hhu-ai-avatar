"""Privacy revision changes invalidate automatic mood, not ordinary turn activity."""
import pytest
from avatar.brain.emotion import EmotionEngine


def engine():
    now=[0.0]
    return EmotionEngine(clock=lambda:now[0],half_life_seconds=60),now


def test_same_revision_keeps_completed_observation_role_and_activity():
    emotion,now=engine();emotion.bind_context_revision(0)
    emotion.observe(-.4,.3,text='面试失利。');energy=emotion.energy
    assert emotion.bind_context_revision(0) is False
    assert emotion.user_state.valence==-.4 and emotion.user_state.arousal==.3
    assert emotion.state.valence==.05 and emotion.state.arousal==-.2 and emotion.energy==energy
    now[0]=60
    assert emotion.state.valence==pytest.approx(.025) and emotion.state.arousal==pytest.approx(-.1)
    assert emotion.user_state.valence==-.4  # Latest observation is not role decay.


def test_new_revision_clears_observation_expression_activity_and_private_text():
    emotion,now=engine();emotion.bind_context_revision(0);emotion.observe(-.4,.3,text='已被遗忘的私人表达。')
    now[0]=17
    assert emotion.bind_context_revision(1) is True
    assert emotion.context_revision==1
    assert (emotion.user_state.valence,emotion.user_state.arousal,emotion.state.valence,emotion.state.arousal)==(0,0,0,0)
    assert emotion.energy==.5 and emotion._observation_text=='' and not emotion._has_observation
    decision=emotion.decide('文件的代号是什么？')
    assert decision.style=='清晰耐心' and decision.speech_rate=='+0%'
    assert 'valence=0.00, arousal=0.00' in decision.persona_hint


def test_unknown_unbound_values_are_not_authorized_by_first_revision():
    emotion,_=engine();emotion.observe(-.4,.3,text='无可核验来源的旧观测。')
    assert emotion.context_revision is None
    emotion.bind_context_revision(7)
    assert emotion.user_state.valence==emotion.state.valence==emotion.state.arousal==0 and emotion.energy==.5


def test_revision_reset_keeps_injected_clock_and_configured_decay():
    now=[0.0];emotion=EmotionEngine(clock=lambda:now[0],decay=.5,half_life_seconds=45)
    emotion.bind_context_revision(1);emotion.observe(.6,.4);emotion.bind_context_revision(2)
    emotion.observe(.6,.4);now[0]=1
    assert emotion.state.valence==pytest.approx(.15) and emotion.state.arousal==pytest.approx(.1)
    assert emotion.decay==.5 and emotion.half_life_seconds==45


def test_old_turn_mark_after_reentrant_reset_cannot_authorize_stale_delta():
    emotion,_=engine();emotion.bind_context_revision(0);emotion.observe(-.4,.3)
    emotion.bind_context_revision(1)  # A public correction during an old update.
    emotion.observe(-.4,.3,text='旧回合迟到结果。');emotion.mark_context_revision(0)
    assert emotion.context_revision==0
    emotion.bind_context_revision(1)
    assert emotion.user_state.valence==emotion.state.valence==emotion.state.arousal==0


def test_database_replacement_with_lower_revision_also_invalidates_old_state():
    emotion,_=engine();emotion.bind_context_revision(5);emotion.observe(.6,.4)
    emotion.bind_context_revision(0)
    assert emotion.context_revision==0 and emotion.state.valence==0 and emotion.user_state.valence==0


@pytest.mark.parametrize('revision',[None,True,False,-1,0.0,'1',float('nan')])
@pytest.mark.parametrize('operation',['bind_context_revision','mark_context_revision'])
def test_invalid_revision_rejected_without_changing_valid_observation(revision,operation):
    emotion,_=engine();emotion.bind_context_revision(0);emotion.observe(-.4,.3,text='有效来源。')
    with pytest.raises(ValueError):getattr(emotion,operation)(revision)
    assert emotion.context_revision==0 and emotion.user_state.valence==-.4 and emotion.state.arousal==-.2
