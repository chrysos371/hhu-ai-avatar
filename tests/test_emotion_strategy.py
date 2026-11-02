"""User observations, elapsed role decay and explicit response strategies."""
import pytest

from avatar.brain.emotion import Decision, EmotionEngine


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def test_angry_observation_does_not_become_roles_anger():
    engine = EmotionEngine()
    role = engine.observe(-0.9, 0.9, "我很生气")
    assert engine.user_state.valence == -0.9
    assert engine.user_state.arousal == 0.9
    assert role is engine.state
    assert role is not engine.user_state
    assert role.valence >= 0
    assert role.arousal <= 0
    assert role.label() != "生气/焦躁"


def test_latest_user_observation_replaces_previous_mood():
    engine = EmotionEngine()
    engine.update_from(-0.9, 0.9)
    engine.update_from(0.2, -0.1)
    assert engine.user_state.valence == 0.2
    assert engine.user_state.arousal == -0.1


def test_idle_role_decays_with_clock_without_decaying_user_observation():
    clock = Clock()
    engine = EmotionEngine(decay=0.5, clock=clock)
    engine.observe(0.8, 0.6)
    valence, arousal = engine.state.valence, engine.state.arousal
    clock.now += 2
    assert engine.state.valence == pytest.approx(valence / 4)
    assert engine.state.arousal == pytest.approx(arousal / 4)
    assert engine.user_state.valence == 0.8
    assert engine.user_state.arousal == 0.6


def test_decisions_at_same_time_do_not_add_decay():
    clock = Clock()
    engine = EmotionEngine(decay=0.5, clock=clock)
    engine.observe(0.8, 0.6)
    before = (engine.state.valence, engine.state.arousal)
    for _ in range(5):
        engine.decide("你好")
    assert (engine.state.valence, engine.state.arousal) == before
    clock.now += 1
    engine.decide("你好")
    assert engine.state.valence == pytest.approx(before[0] / 2)


def test_explicit_decay_step_still_relaxes_role_only():
    clock = Clock()
    engine = EmotionEngine(decay=0.5, clock=clock)
    engine.observe(-0.8, 0.8)
    before = engine.state.arousal
    engine.decay_step()
    assert engine.state.arousal == pytest.approx(before / 2)
    assert engine.user_state.arousal == 0.8


@pytest.mark.parametrize("text", [
    "我很难过，不要给我建议，只想说说", "我很烦，你听我说就好",
    "我很焦虑，不用帮我制定计划，只想倾诉", "我不需要建议",
])
def test_explicit_no_advice_selects_listen(text):
    engine = EmotionEngine()
    engine.update(text)
    decision = engine.decide(text)
    assert decision.strategy == "listen"
    assert "建议" in decision.persona_hint


@pytest.mark.parametrize("text", [
    "我很焦虑，帮我制定复习计划", "别安慰我了，帮我分析怎么复习",
    "我不是不想要建议，帮我安排复习", "请告诉我如何复习",
])
def test_practical_request_overrides_emotional_language(text):
    engine = EmotionEngine()
    engine.update("我很难过，好伤心")
    engine.update(text)
    assert engine.decide(text).strategy == "advise"
    assert EmotionEngine.classify_intent(text) == "指令"


def test_new_question_exits_previous_support_strategy():
    engine = EmotionEngine()
    engine.update("我很难过")
    assert engine.decide("我很难过").strategy == "empathize"
    assert engine.decide("什么是大模型？").strategy == "answer"


@pytest.mark.parametrize("text", ["我考上研究生了！", "我通过考试了，太开心了！", "我的申请成功了！", "刚查到成绩改正了，我及格啦！"])
def test_positive_news_selects_celebration(text):
    engine = EmotionEngine()
    engine.update(text)
    assert engine.decide(text).strategy == "celebrate"


@pytest.mark.parametrize("text", ["我没考上研究生，好失望", "我不开心", "我没通过考试", "我没及格"])
def test_negated_positive_news_does_not_trigger_celebration(text):
    engine = EmotionEngine()
    engine.update(text)
    assert engine.decide(text).strategy != "celebrate"


def test_angry_user_resets_previous_excitement_and_gets_steady_support():
    engine = EmotionEngine()
    engine.update("太开心了，超级兴奋！！")
    engine.update("我生气了，简直要崩溃！！")
    decision = engine.decide("我生气了，简直要崩溃！！")
    assert decision.strategy == "empathize"
    assert "活泼" not in decision.style
    assert "乐观" not in decision.persona_hint
    assert int(decision.speech_rate.rstrip("%")) <= 0
    assert engine.state.valence >= 0
    assert engine.user_state.valence < 0


@pytest.mark.parametrize("text", ["我喜欢喝咖啡", "我不喜欢吃香菜", "我讨厌吃香菜"])
def test_ordinary_food_preference_is_not_a_mood(text):
    engine = EmotionEngine()
    engine.update(text)
    assert engine.user_state.valence == 0
    assert engine.decide(text).strategy == "answer"


def test_vague_help_request_asks_for_clarification():
    assert EmotionEngine().decide("帮帮我").strategy == "clarify"


def test_legacy_decision_constructor_still_works():
    decision = Decision("清晰", 0.3, "+0%", "+0Hz", 0.7, "清晰回答")
    assert decision.strategy == "answer"


def test_negation_checks_each_occurrence_not_only_the_first():
    engine = EmotionEngine()
    valence, _ = engine.infer("我不开心，后来真的开心了")
    assert valence == pytest.approx(0.0)


def test_double_negation_does_not_invert_positive_mood():
    valence, _ = EmotionEngine().infer("我不是不开心")
    assert valence > 0


@pytest.mark.parametrize("text", ["别给建议", "先别出主意", "不用帮我想办法", "不想听建议"])
def test_no_advice_paraphrases_select_listen(text):
    assert EmotionEngine().decide(text).strategy == "listen"


def test_no_advice_negation_is_not_confused_with_reminder_for_advice():
    assert EmotionEngine().decide("不要忘了给我建议").strategy == "advise"


def test_food_preference_does_not_hide_mood_in_same_sentence():
    engine = EmotionEngine()
    engine.update("我喜欢喝咖啡，但今天很难过")
    assert engine.user_state.valence < 0
    assert engine.decide("我喜欢喝咖啡，但今天很难过").strategy == "empathize"


def test_neutral_external_observation_is_authoritative():
    engine = EmotionEngine()
    engine.observe(0.0, 0.0, "我喜欢你")
    assert engine.decide("我喜欢你").strategy == "answer"


@pytest.mark.parametrize("text", [
    "别告诉我怎么做，我现在很难过",
    "不要帮我分析怎么复习，我现在很难过",
    "我不想听你的建议，告诉我你理解我的感受就好",
    "不需要帮我分析怎么复习，我现在很难过",
    "我不需要你告诉我怎么做，我现在很难过",
    "不用告诉我应该怎么做，我现在很难过",
])
def test_negated_practical_request_keeps_explicit_no_advice_strategy(text):
    engine = EmotionEngine()
    engine.update(text)
    assert engine.decide(text).strategy == "listen"
    assert EmotionEngine.classify_intent(text) == "情感倾诉"


@pytest.mark.parametrize("text", [
    "我不是不需要你告诉我怎么做，我需要复习建议",
    "不是不要帮我分析怎么复习，我想要建议",
    "我并非不用你告诉我应该怎么做，帮我制定计划",
])
def test_double_negated_practical_request_still_allows_advice(text):
    assert EmotionEngine().decide(text).strategy == "advise"
