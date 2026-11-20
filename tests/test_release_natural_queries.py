"""Finite ordinary-chat aliases for existing authenticated read services."""
from contextlib import closing

import pytest

from avatar.brain.memory import MemoryStore
from avatar.main import Avatar
from test_capability_prompt_lab import Recorder
from test_reminder_query_flow import seed,projection,SECRET


@pytest.mark.parametrize('text,route',[
    ('提醒编号1现在是什么状态？','read_state'),
    ('提醒编号1取消了吗？','read_state'),
    ('提醒编号1还有效吗？','read_state'),
    ('程序退出后提醒还能发短信吗？','read_policy'),
])
def test_actual_chat_alias_uses_real_read_without_model_or_due_claim(text,route):
    with closing(MemoryStore(':memory:')) as memory:
        seed(memory,due=True);before=projection(memory);model=Recorder('不应生成')
        bot=Avatar(memory=memory,llm=model,capability_contract_enabled=True,role_state_enabled=True)
        result=bot.respond(text)
        assert result['generation_mode']=='rules_reminder_query'
        assert result['reminder_query']['route']==route and result['reminder_query']['version']==2
        assert projection(memory)==before and not model.analysis and not model.native
        assert not result['due_reminders'] and not result['action_receipts']['items']


@pytest.mark.parametrize('text',[
    '“提醒编号1现在是什么状态？”', '写一句“提醒编号1现在是什么状态？”的台词。',
    '不要查询提醒编号1现在是什么状态。','提醒编号1现在是什么状态？然后取消它。',
])
def test_quoted_negated_or_mixed_whole_messages_do_not_gain_read_authority(text):
    with closing(MemoryStore(':memory:')) as memory:
        seed(memory,due=False)
        result=Avatar(memory=memory,llm=Recorder('普通草稿'),capability_contract_enabled=True,role_state_enabled=True).respond(text)
        assert 'reminder_query' not in result and SECRET not in result['reply']


def test_fictional_scope_cannot_use_the_natural_alias_to_read_a_real_record():
    with closing(MemoryStore(':memory:')) as memory:
        seed(memory,due=False)
        bot=Avatar(memory=memory,llm=Recorder('普通对白'),capability_contract_enabled=True,role_state_enabled=True)
        bot.respond('我来扮演一个虚构角色。')
        result=bot.respond('提醒编号1现在是什么状态？')
        assert result['generation_mode']=='rules_speaker_scope' and SECRET not in result['reply']
