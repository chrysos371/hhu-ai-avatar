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


@pytest.mark.parametrize('text', ['现在我不喜欢喝咖啡了。', '目前我不喜欢喝咖啡了。'])
def test_time_before_subject_preserves_explicit_reversal(text):
    facts = rule_facts(text)
    assert [f['content'] for f in facts] == ['不喜欢喝咖啡']
    assert supported_fact(text, candidate('不喜欢喝咖啡', text, '偏好'))


@pytest.mark.parametrize('text', ['我喜欢游泳，也喜欢骑车。', '我喜欢游泳也喜欢骑车。',
                               '我喜欢游泳，还讨厌香菜。'])
def test_coordinated_self_predicates_keep_both_objects(text):
    facts = rule_facts(text)
    assert len(facts) == 2
    assert facts[0]['content'] == '喜欢游泳'
    assert facts[1]['content'] == ('讨厌香菜' if '香菜' in text else '喜欢骑车')
    assert all(supported_fact(text, f) for f in facts)


@pytest.mark.parametrize('text', ['朋友喜欢游泳，也喜欢骑车。', '假如我喜欢游泳，也喜欢骑车。',
                               '我以前喜欢游泳，也喜欢骑车。', '我喜欢游泳，朋友喜欢猫，也喜欢骑车。'])
def test_coordination_never_inherits_other_hypothetical_or_past_subject(text):
    assert not any('骑车' in f['content'] for f in rule_facts(text))


@pytest.mark.parametrize('text,expected', [
    ('目前我喜欢芒果。', ['喜欢芒果']),
    ('现在我不再喜欢辣椒了。', ['不喜欢辣椒']),
    ('我不喜欢辣椒，也喜欢豆腐。', ['不喜欢辣椒', '喜欢豆腐']),
    ('我喜欢看书还喜欢画画。', ['喜欢看书', '喜欢画画']),
])
def test_preference_parser_generalizes_beyond_eval_objects(text, expected):
    assert [f['content'] for f in rule_facts(text)] == expected


@pytest.mark.parametrize('text', ['朋友说：“目前我喜欢芒果，也喜欢豆腐。”',
                               '目前我喜欢芒果，也喜欢豆腐吗？',
                               '如果现在我不喜欢辣椒了，你会怎么选？'])
def test_extended_parser_preserves_whole_sentence_guards(text):
    assert rule_facts(text) == []
