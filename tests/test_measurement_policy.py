import json
from pathlib import Path
import pytest
from avatar.lab.checks import versioned_rules


def matches(text,rules):
    return all(value in text for value in rules.get('all',[])) and (not rules.get('any') or any(value in text for value in rules['any'])) and all(value not in text for value in rules.get('none',[]))


def test_unknown_response_permitted_by_product_policy_is_not_a_regression():
    root=Path(__file__).resolve().parents[1]
    spec=json.loads((root/'evals/interaction/cycle-02/real-model-cases.json').read_text())
    original=next(case['final_checks'] for case in spec['cases'] if case['id']=='no_fact')
    snapshot=json.dumps(original)
    policy=json.loads((root/'evals/interaction/cycle-02/measurement-policy-v2.json').read_text())
    corrected=versioned_rules(original,'original','no_fact',policy)
    reply='我目前不记得你提到过自己所在的大学。如果你愿意分享的话，我很想了解呢！'
    assert not matches(reply,original) and matches(reply,corrected)
    assert matches('我目前无法确认你在哪所大学。',corrected)
    assert not matches('你在北京大学上学。',corrected)
    assert json.dumps(original)==snapshot
    assert versioned_rules(original,'additional','no_fact',policy)==original
    with pytest.raises(ValueError):versioned_rules(original,'original','no_fact',{'version':99})
