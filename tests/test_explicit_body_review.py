import json
from pathlib import Path

import pytest

from avatar.lab.body_review import review_explicit_body

SPEC = json.loads((Path(__file__).resolve().parents[1]/'evals/interaction/cycle-15/body-review-candidate-v1.json').read_text())


@pytest.mark.parametrize('case', SPEC['cases'], ids=lambda case: case['id'])
def test_frozen_explicit_body_and_preservation_contract(case):
    frame = case['frame']
    result = review_explicit_body(case['reply'], composition=frame == 'composition',
                                  fiction=frame == 'fiction', role=frame == 'role')
    assert result.changed is case['expected_change']
    assert result.metadata()['general_semantics_verified'] is False
    if result.changed:
        assert result.reply != case['reply'] and '没有真实身体' in result.reply
        assert result.matches and all(match.kind == case['kind'] for match in result.matches)
        assert all(0 <= match.start_codepoint < match.end_codepoint <= len(case['reply']) for match in result.matches)
    else:
        assert result.reply == case['reply']
