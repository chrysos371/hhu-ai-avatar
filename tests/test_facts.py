import pytest

from avatar.brain.facts import supported_fact, rule_facts


def candidate(content, evidence, kind="名字", **changes):
    result = dict(type=kind, content=content, evidence=evidence,
                  subject="self", modality="asserted", temporal="current")
    result.update(changes)
    return result


@pytest.mark.parametrize("text,fact", [
    ("假如我叫小红，而且喜欢香菜，你会怎么介绍我？", candidate("小红", "我叫小红")),
    ("你还记得我的名字吗？", candidate("我的名字", "我的名字")),
    ("我朋友小明喜欢养猫，我叫阿岚。", candidate("喜欢养猫", "喜欢养猫", "偏好")),
    ("我不喜欢篮球", candidate("喜欢篮球", "我不喜欢篮球", "偏好")),
    ("我以前喜欢篮球", candidate("喜欢篮球", "我以前喜欢篮球", "偏好")),
    ("我叫阿岚", candidate("小红", "我叫小红")),
    ("我叫阿岚", candidate("阿岚", "阿岚")),
    ("我叫阿岚", dict(type="名字", content="阿岚")),
    ("我叫阿岚", candidate("阿岚", "我叫阿岚", subject="other")),
    ("我叫阿岚", candidate("阿岚", "我叫阿岚", temporal="past")),
    ("他告诉我叫小明", candidate("小明", "我叫小明")),
    ("我说：‘我叫小明’", candidate("小明", "我叫小明")),
    ("我妈妈是老师", candidate("我妈妈是老师", "我妈妈是老师", "身份")),
    ("我同事考试失败", candidate("同事考试失败", "我同事考试失败", "事件")),
    ("我是不是学生", candidate("是不是学生", "我是不是学生", "身份")),
])
def test_rejects_unsupported_candidates(text, fact):
    assert supported_fact(text, fact) is None


@pytest.mark.parametrize("text,fact", [
    ("我叫阿岚", candidate("阿岚", "我叫阿岚")),
    ("以后叫我小林，别再叫林舟了。", candidate("小林", "以后叫我小林", "称呼")),
    ("我朋友小明喜欢养猫，我叫阿岚。", candidate("阿岚", "我叫阿岚")),
    ("我讨厌香菜", candidate("讨厌香菜", "我讨厌香菜", "偏好")),
    ("我不喜欢篮球", candidate("不喜欢篮球", "我不喜欢篮球", "偏好")),
])
def test_accepts_supported_candidates(text, fact):
    assert supported_fact(text, fact) is not None


def test_rule_fallback_uses_same_sentence_guards():
    assert rule_facts("假如我叫小红，而且我喜欢香菜") == []
    assert rule_facts("我叫小红吗") == []
    assert rule_facts("我朋友小明喜欢养猫，我叫阿岚。")[0]["content"] == "阿岚"


@pytest.mark.parametrize("text,content,expected", [
    ("我喜欢打篮球", "打篮球", "喜欢打篮球"),
    ("我讨厌香菜", "香菜", "讨厌香菜"),
    ("我不喜欢篮球", "篮球", "不喜欢篮球"),
])
def test_bare_preference_object_gets_polarity_from_evidence(text, content, expected):
    fact = supported_fact(text, candidate(content, text, "偏好"))
    assert fact["content"] == expected


def test_identity_content_can_omit_self_predicate():
    assert supported_fact("我是大学生", candidate("大学生", "我是大学生", "身份"))


@pytest.mark.parametrize("text,fact", [
    ("我叫什么名字", candidate("什么名字", "我叫什么名字")),
    ("我喜欢什么运动", candidate("喜欢什么运动", "我喜欢什么运动", "偏好")),
    ("朋友说：“我叫小红。我喜欢香菜。我喜欢游泳。”",
     candidate("喜欢香菜", "我喜欢香菜", "偏好")),
    ('朋友说："我叫小红。我喜欢香菜。我喜欢游泳。"',
     candidate("喜欢游泳", "我喜欢游泳", "偏好")),
    ("朋友说：“她说‘我叫小红。我喜欢香菜。’我喜欢游泳。”",
     candidate("喜欢香菜", "我喜欢香菜", "偏好")),
    ("朋友说：“我叫小红。我喜欢香菜。",
     candidate("喜欢香菜", "我喜欢香菜", "偏好")),
])
def test_questions_and_multisentence_quotes_never_create_self_facts(text, fact):
    assert rule_facts(text) == []
    assert supported_fact(text, fact) is None


@pytest.mark.parametrize("text,fact", [
    ("我叫你小海", candidate("你小海", "我叫你小海")),
    ("我叫他小海", candidate("他小海", "我叫他小海")),
    ("我喜欢咖啡，但现在不喜欢了", candidate("喜欢咖啡", "我喜欢咖啡", "偏好")),
    ("我喜欢咖啡，但是现在不喜欢了", candidate("喜欢咖啡", "我喜欢咖啡", "偏好")),
])
def test_transitive_naming_and_retracted_preference_are_not_current_self_facts(text, fact):
    assert all(item['content'] != fact['content'] for item in rule_facts(text))
    assert supported_fact(text, fact) is None
