"""A finite source-built artifact must disclose failed model repair and its scope."""
from contextlib import closing
import re

import pytest

from avatar.brain.memory import MemoryStore
from avatar.cancellation import CancellationToken, Cancelled
from avatar.main import Avatar
from test_writing_delivery_contract import Replies


@pytest.mark.parametrize('count', [1,2,3])
def test_simple_unknown_leave_fields_render_from_sources_after_two_failed_calls(count):
    with closing(MemoryStore(':memory:')) as memory:
        engine = Replies(['今天身体不适。', '因个人原因请假。'])
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        result = bot.respond(f'麻烦给导师写一封请假邮件，署名用【申请人】，改成{count}句话，只给正文。')
        assert result['generation_mode'] == 'rules_writing_artifact'
        assert len(engine.native) == 2 and not result['writing_delivery']['repair_succeeded']
        fallback = result['writing_delivery']['source_fallback']
        assert fallback['used'] and fallback['semantic_verifier'] is False
        assert '【请假原因】' in result['reply'] and '【申请人】' == result['reply'].splitlines()[-1]
        assert len(re.findall(r'[。！？!?]+', result['reply'])) == count
        assert not result['writing_delivery']['final_issues']
        assert result['writing_delivery']['model_repair_issues']
        assert memory.get_short_term()[-1]['content'] == result['reply']
        assert not result['tool_calls'] and not result['action_receipts']


def test_given_event_stays_verbatim_and_unprovided_duration_is_not_added():
    with closing(MemoryStore(':memory:')) as memory:
        engine = Replies(['明天请假一天。', '明天参加家里的活动，请假一天。'])
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        result = bot.respond('帮我写一条请假短信，我明天要参加家里的活动，只给正文。')
        assert result['generation_mode'] == 'rules_writing_artifact'
        assert '我明天要参加家里的活动' in result['reply']
        assert '一天' not in result['reply'] and '个人原因' not in result['reply']


@pytest.mark.parametrize('request_text', [
    '帮我写一条请假短信，必须保留“不可丢失素材”。',
    '替姐姐给老师写一封请假邮件。',
    '帮我写一条请假短信，明确说明尚未获批准。',
])
def test_unhandled_material_perspective_or_status_never_silently_dropped(request_text):
    with closing(MemoryStore(':memory:')) as memory:
        engine = Replies(['今天身体不适。', '今天身体不适。'])
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        result = bot.respond(request_text)
        assert result['generation_mode'] == 'rules_writing_validation'
        assert not result['writing_delivery']['source_fallback']['used']


def test_fictional_counterparty_author_and_receipt_do_not_become_real_execution():
    with closing(MemoryStore(':memory:')) as memory:
        bad = '老师您好，我已将邮件发送给您，希望您能尽快回复。'
        engine = Replies(['开始吧。', bad, bad])
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        bot.respond('我来扮演小说角色。')
        result = bot.respond('我已把邮件发给老师，接着写对方回复。')
        assert result['writing_requirements']['author_role'] == '老师'
        assert 'wrong_artifact_author' in result['writing_delivery']['initial_issues']
        assert result['generation_mode'] == 'rules_writing_artifact'
        assert '老师您好' not in result['reply'] and '你好' in result['reply']
        assert not result['tool_calls'] and not result['action_receipts']
