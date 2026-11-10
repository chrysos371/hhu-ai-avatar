import json
from pathlib import Path
import pytest
from avatar.brain.tasks import TaskTracker

SPEC=json.loads((Path(__file__).resolve().parents[1]/'evals/interaction/cycle-03/task-followup24.json').read_text())


@pytest.mark.parametrize('case',SPEC['cases'],ids=lambda case:case['id'])
def test_edit_commands_do_not_turn_new_questions_into_old_deliverables(case):
    tracker=TaskTracker()
    for text in case['turns']:tracker.update(text)
    assert bool(tracker.current)==case['expected_active']


def test_explicit_cancel_then_new_writing_request_starts_fresh_contract():
    tracker=TaskTracker()
    tracker.update('给老师写一条消息，保留“甲”。')
    tracker.update('取消这个任务，给朋友写一条新消息，包含“乙”。')
    assert tracker.current.required_literals==['乙']
    assert tracker.current.recipient=='朋友'
