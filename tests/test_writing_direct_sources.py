"""Source-built operations must not depend on recognizing every bad model phrase."""
from contextlib import closing

import pytest

from avatar.brain.memory import MemoryStore
from avatar.main import Avatar
from avatar.cancellation import CancellationToken, Cancelled
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


@pytest.mark.parametrize('change',['forget','cancel'])
def test_actual_change_during_direct_source_construction_prevents_any_output(tmp_path, monkeypatch, change):
    from avatar.brain import writing_templates
    with closing(MemoryStore(str(tmp_path/'direct.db'))) as memory:
        engine=Replies(['甲'])
        bot=Avatar(memory=memory,llm=engine,capability_contract_enabled=True)
        token, pieces=CancellationToken(),[]
        original=writing_templates.build_fallback
        def changed(requirements,**kwargs):
            result=original(requirements,**kwargs)
            assert result is not None
            if change=='cancel':token.cancel()
            else:
                fragment=memory.remember('有来源的原样文字',source_message_id=requirements.source_message_ids[0])
                with closing(MemoryStore(memory.db_path)) as writer:writer.forget(fragment)
            return result
        monkeypatch.setattr(writing_templates,'build_fallback',changed)
        with pytest.raises(Cancelled):bot.respond('原样输出这句话：“甲”',cancel=token,on_delta=pieces.append)
        assert not pieces and not engine.native
        assert not memory._conn.execute("SELECT 1 FROM memory_messages WHERE role='assistant'").fetchone()
