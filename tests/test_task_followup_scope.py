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
