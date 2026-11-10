import json
from pathlib import Path
import pytest
from avatar.main import Avatar

SPEC=json.loads((Path(__file__).resolve().parents[1]/'evals/interaction/cycle-03/literal-reminder8.json').read_text())


@pytest.mark.parametrize('case',SPEC['cases'],ids=lambda case:case['id'])
def test_writing_reminder_text_is_separate_from_authorized_reminder_action(case):
    class Offline:
        available=False
    avatar=Avatar(db_path=':memory:',llm=Offline(),task_contract_enabled=True,delivery_check_enabled=True)
    try:
        for text in case['turns']:result=avatar.respond(text)
        assert bool(result['task'])==case['expected_contract_active']
        assert len(avatar.reminders.list())==case['expected_reminder_count']
    finally:avatar.memory.close()
