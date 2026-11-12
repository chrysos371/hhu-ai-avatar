"""Clean natural control and one-variable grammar contrast in paired plan arms."""
from hashlib import sha256
import json
from pathlib import Path
import sys
import pytest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import native_evidence_plan_v2 as subject
from native_evidence_plan import SYSTEM


@pytest.fixture
def protocol():return json.loads((ROOT/'evals/interaction/cycle-28/source-atom-three-arm-protocol.json').read_text())


def test_protocol_is_known_case_replay_without_hidden_case_or_gold_changes(protocol):
    old_path=ROOT/protocol['source_protocol'];old=json.loads(old_path.read_text())
    assert sha256(old_path.read_bytes()).hexdigest()==protocol['source_protocol_sha256']
    assert protocol['cases']==old['cases'] and len(protocol['cases'])==12


def test_plan_arms_share_exact_messages_and_only_schema_differs(protocol):
    for case in protocol['cases']:
        free=subject.payload(case,'plan_free');constrained=subject.payload(case,'plan_schema')
        assert free['messages']==constrained['messages']
        format_value=constrained.pop('response_format');assert constrained==free
        assert format_value['json_schema']['strict'] is True


def test_natural_prompt_cannot_tell_model_to_select_internal_plan_operations(protocol):
    case=protocol['cases'][0];message=subject.payload(case,'natural')['messages'][0]['content']
    assert '自然语言' in message and 'JSON' in message  # Explicitly forbids JSON.
    assert all(word not in message for word in ['operation','reference','copy_draft','insufficient_evidence','response_format'])
    assert 'response_format' not in subject.payload(case,'natural')


def test_all_arms_share_question_context_with_no_gold_or_case_ids(protocol):
    for case in protocol['cases']:
        values=[subject.payload(case,arm)['messages'][-1] for arm in subject.ARMS]
        assert values[0]==values[1]==values[2]
        assert json.loads(values[0]['content'])=={'question':case['question'],'context':case['context']}


def test_operation_policy_is_unchanged_from_c27_but_format_is_visible():
    rules=SYSTEM[SYSTEM.index('capability_boundary用于'):SYSTEM.index('输出格式由请求')]
    assert rules in subject.PLAN_SYSTEM
    assert 'response_format' not in subject.PLAN_SYSTEM and '如果返回' not in subject.PLAN_SYSTEM
    assert 'JSON' in subject.PLAN_SYSTEM


def test_unknown_arm_does_not_fall_back_to_an_unconstrained_request(protocol):
    with pytest.raises(ValueError):subject.payload(protocol['cases'][0],'unregistered')
