import json
from pathlib import Path

import pytest

from avatar.brain.tasks import TaskTracker

SPEC=json.loads((Path(__file__).resolve().parents[1]/'evals/interaction/cycle-03/literal-contract24.json').read_text())


@pytest.mark.parametrize('case',SPEC['cases'],ids=lambda case:case['id'])
def test_frozen_literal_contract_scope(case):
    tracker=TaskTracker()
    for text in case['turns']:tracker.update(text)
    assert bool(tracker.current)==case['active']
    if tracker.current:
        assert tracker.current.required_literals==case['required']
        assert tracker.current.forbidden_literals==case['forbidden']
        for literal in case['required']:
            assert 'missing_literal:'+literal in tracker.inspect('')
        for literal in case['forbidden']:
            assert 'forbidden_literal:'+literal in tracker.inspect(literal)


def test_quoted_task_content_cannot_change_writer_role_or_recipient():
    tracker=TaskTracker()
    tracker.update('请给我写一条短信，内容是“替我姐姐给老师解释”。')
    assert tracker.current.perspective==''
    assert tracker.current.recipient==''
