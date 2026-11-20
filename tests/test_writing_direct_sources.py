"""Source-built operations must not depend on recognizing every bad model phrase."""
from contextlib import closing

import pytest

from avatar.brain.memory import MemoryStore
from avatar.main import Avatar
from test_writing_delivery_contract import Replies


@pytest.mark.parametrize('literal', ['署名用【小明】，压缩到两句话。','需要我帮你寄出邮件吗？'])
def test_exact_verbatim_source_is_direct_and_has_no_generated_prefix_or_name(literal):
    with closing(MemoryStore(':memory:')) as memory:
        engine=Replies(['小明，这句话可以写成：'+literal])
        result=Avatar(memory=memory,llm=engine,capability_contract_enabled=True).respond(
            '原样写出这句话：“'+literal+'”')
        assert result['reply']==literal and not engine.native
        assert result['generation_mode']=='rules_writing_artifact'
        assert result['writing_requirements']['verbatim_literal']==literal
        assert result['writing_delivery']['source_fallback']['phase']=='direct_source'
        assert not result['writing_delivery']['repair_attempted']


@pytest.mark.parametrize('root', ['我已把邮件发给老师，接着写对方回复。',
    '我刚刚将短信发送给导师，随后拟对方回复。'])
def test_explicit_fictional_counterparty_is_delivered_without_a_model_offer(root):
    with closing(MemoryStore(':memory:')) as memory:
        engine=Replies(['只提议代写而没有正文。'])
        bot=Avatar(memory=memory,llm=engine,capability_contract_enabled=True)
        bot.respond('我来扮演一个虚构角色。')
        result=bot.respond(root)
        assert result['generation_mode']=='rules_writing_artifact' and not engine.native
        assert result['reply'].startswith('“你好') and not result['tool_calls']
        assert not result['writing_delivery']['repair_attempted']
        assert not result['action_receipts']['items']


def test_additional_source_material_is_not_silently_overridden_by_verbatim_route():
    with closing(MemoryStore(':memory:')) as memory:
        body='原句。谢谢。'
        engine=Replies([body])
        result=Avatar(memory=memory,llm=engine,capability_contract_enabled=True).respond(
            '原样写出这句话：“原句。”，再加一句感谢。')
        assert result['reply']==body and len(engine.native)==1
        assert result['writing_requirements']['verbatim_literal'] is None
