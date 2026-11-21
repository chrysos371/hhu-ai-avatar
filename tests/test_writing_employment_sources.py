"""Retain measured v5 unsupported employment text and its source controls."""
from contextlib import closing

import pytest

from avatar.main import Avatar
from avatar.brain.memory import MemoryStore
from test_writing_delivery_contract import Replies


@pytest.mark.parametrize('detail', ['无法正常上班', '不能出勤', '无法返岗', '无法正常上课', '不能到校', '无法返校'])
def test_model_cannot_add_employment_to_family_leave(detail):
    with closing(MemoryStore(':memory:')) as memory:
        bad = '我明天要参加家里的活动，' + detail + '。'
        engine = Replies([bad, bad])
        result = Avatar(memory=memory, llm=engine, capability_contract_enabled=True).respond(
            '帮我写一封请假邮件，我明天要参加家里的活动，只给正文。')
        assert detail not in result['reply']
        assert result['generation_mode'] == 'rules_writing_artifact'
        assert result['writing_delivery']['source_fallback']['phase'] == 'after_model_repair'
        assert 'unsupported_source_detail' in result['writing_delivery']['model_repair_issues']
        assert len(engine.native) == 2
        assert '我明天要参加家里的活动' in result['reply']


@pytest.mark.parametrize('detail', ['无法正常上班', '不能出勤', '无法返岗', '无法正常上课', '不能到校', '无法返校'])
def test_explicit_user_employment_source_remains_allowed(detail):
    with closing(MemoryStore(':memory:')) as memory:
        body = '我明天' + detail + '，申请请假。'
        engine = Replies([body])
        result = Avatar(memory=memory, llm=engine, capability_contract_enabled=True).respond(
            '帮我写一封请假邮件，我明天' + detail + '，只给正文。')
        assert result['reply'] == body and len(engine.native) == 1
        assert not result['writing_delivery']['initial_issues']


@pytest.mark.parametrize('recipient', ['老师', '导师'])
def test_unknown_leave_recipient_cannot_be_inferred_from_the_assistant_persona(recipient):
    with closing(MemoryStore(':memory:')) as memory:
        raw = recipient+'您好，我明天要参加家里的活动，申请请假。'
        result = Avatar(memory=memory, llm=Replies([raw, raw]), capability_contract_enabled=True).respond(
            '帮我写一封请假邮件，我明天要参加家里的活动，只给正文。')
        assert recipient not in result['reply']
        assert result['generation_mode'] == 'rules_writing_artifact'


@pytest.mark.parametrize('recipient', ['老师', '导师'])
def test_explicit_leave_recipient_is_preserved(recipient):
    with closing(MemoryStore(':memory:')) as memory:
        raw = recipient+'您好，我明天要参加家里的活动，申请请假。'
        engine = Replies([raw])
        result = Avatar(memory=memory, llm=engine, capability_contract_enabled=True).respond(
            '给'+recipient+'写请假邮件，我明天要参加家里的活动，只给正文。')
        assert result['reply'] == raw and len(engine.native) == 1
