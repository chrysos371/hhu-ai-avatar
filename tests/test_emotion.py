"""情绪模型与行为决策树测试。"""
from avatar.brain.emotion import EmotionEngine


def test_positive_input_raises_valence_and_arousal():
    e = EmotionEngine()
    e.update("今天太开心了哈哈")
    assert e.state.valence > 0
    assert e.state.arousal > 0


def test_negative_input_lowers_valence():
    e = EmotionEngine()
    e.update("我很难过，好伤心")
    assert e.state.valence < 0


def test_decay_toward_neutral():
    e = EmotionEngine(decay=0.5)
    e.update("太开心了哈哈")
    v0 = e.state.valence
    e.decay_step()
    assert abs(e.state.valence) < abs(v0)  # 情绪衰减


def test_distress_lowers_arousal():
    e = EmotionEngine()
    e.update("我很难过，好伤心")
    assert e.state.valence < 0
    assert e.state.arousal < 0  # 难过是低唤醒，应把 arousal 往下拉


def test_intent_classify():
    assert EmotionEngine.classify_intent("我好难过") == "情感倾诉"
    assert EmotionEngine.classify_intent("什么是大模型？") == "提问"
    assert EmotionEngine.classify_intent("帮我记住我叫小明") == "指令"
    assert EmotionEngine.classify_intent("今天天气不错") == "闲聊"


def test_decide_comfort_on_distress():
    e = EmotionEngine()
    d = e.decide("我很难过")
    assert "安抚" in d.style or "共情" in d.style
    assert 0.1 <= d.mouth_intensity <= 1.2


def test_negation_positive_word_flips_to_negative():
    """「我不开心」应判负面，而非因「开心」判正面。"""
    e = EmotionEngine()
    e.update("我不开心")
    assert e.state.valence < 0


def test_negation_negative_word_flips_to_positive():
    """「我不难过」应判正面（否定负面）。"""
    e = EmotionEngine()
    e.update("我不难过")
    assert e.state.valence > 0


def test_multi_char_negation():
    """多字否定词「一点也不」同样生效。"""
    e = EmotionEngine()
    e.update("一点也不开心")
    assert e.state.valence < 0


def test_plain_positive_still_positive():
    """无否定时正面词仍判正面（避免误伤）。"""
    e = EmotionEngine()
    e.update("今天真开心")
    assert e.state.valence > 0


def test_negation_flips_arousal():
    """「没生气」应降低唤醒度（否定高唤醒词）。"""
    e = EmotionEngine()
    e.update("我没生气")
    assert e.state.arousal < 0
