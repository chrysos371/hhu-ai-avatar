import pytest
from avatar.brain.emotion import EmotionEngine


@pytest.mark.parametrize('text', ['晚安', '我先下了', '今天不聊了，拜拜'])
def test_goodbye_uses_close(text):
    engine = EmotionEngine()
    engine.update(text)
    assert engine.decide(text).strategy == 'close'


@pytest.mark.parametrize('text', ['帮我翻译晚安', '“晚安”是什么意思', '我不想说晚安', '他跟我说晚安'])
def test_mentioned_goodbye_does_not_end_conversation(text):
    assert EmotionEngine().decide(text).strategy != 'close'


def test_activity_separate_from_negative_emotion_and_decays():
    now = [0.]
    engine = EmotionEngine(clock=lambda: now[0])
    for _ in range(20):
        engine.update('我好难过')
    energy = engine.energy
    assert .5 < energy <= 1
    assert engine.decide('我好难过').strategy == 'empathize'
    now[0] = 6 * 3600
    assert engine.energy == pytest.approx(.5 + (energy - .5) / 2)
    before = engine.energy
    engine.decide('我喜欢香菜')
    assert engine.energy == before
