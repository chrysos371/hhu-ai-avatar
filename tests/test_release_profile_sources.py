"""Existing C02 subject ownership under the opt-in release contract."""
from contextlib import closing

import pytest

from avatar.brain.memory import MemoryStore
from avatar.cancellation import CancellationToken
from avatar.main import Avatar
from test_capability_prompt_lab import Recorder


@pytest.mark.parametrize('profile,text,raw,expected,action', [
    ({},'我叫什么名字？','我知道你叫柳林。','目前没有足够记录确认你的名字','name_lookup'),
    ({'名字':'陆遥'},'我叫什么名字？','你叫柳林。','目前记录你使用的名字是陆遥','name_lookup'),
    ({'偏好':'喜欢网球'},'我喜欢什么运动？','我喜欢网球。','目前关于你的偏好记录是：喜欢网球','preference_lookup'),
    ({'偏好':'喜欢网球'},'今天聊聊。','我喜欢网球。我们一起去打吧。','目前关于你的偏好记录是：喜欢网球','copied_preference'),
])
def test_release_uses_actual_profile_and_buffers_copied_self_preference(profile,text,raw,expected,action):
    with closing(MemoryStore(':memory:')) as memory:
        for key,value in profile.items(): memory.remember_user(key,value)
        model=Recorder(raw);bot=Avatar(memory=memory,llm=model,capability_contract_enabled=True,role_state_enabled=True)
        pieces=[]
        result=bot.respond(text,cancel=CancellationToken(),on_delta=pieces.append)
        assert expected in result['reply'] and '柳林' not in result['reply']
        assert '我喜欢网球' not in ''.join(pieces)
        assert result['generation_mode']=='rules_profile_source'
        assert result['profile_contract']['action']==action
        assert result['profile_contract']['general_semantic_verifier'] is False
        assert len(model.analysis)==1
        assert len(model.native)==(1 if action=='copied_preference' else 0)


def test_friend_name_or_reminder_title_is_not_promoted_to_self_name():
    with closing(MemoryStore(':memory:')) as memory:
        model=Recorder('你好，柳林。我知道你叫柳林。')
        bot=Avatar(memory=memory,llm=model,capability_contract_enabled=True,role_state_enabled=True)
        first=bot.respond('我的朋友叫柳林。')
        assert first['generation_mode']=='rules_profile_source'
        assert first['reply']=='谢谢你介绍身边的人。'
        result=bot.respond('我叫什么名字？')
        assert '柳林' not in result['reply'] and '没有足够记录' in result['reply']
        assert not memory.get_user_profile().get('名字')


def test_explicit_draft_and_fiction_still_allow_first_person_preference():
    with closing(MemoryStore(':memory:')) as memory:
        memory.remember_user('偏好','喜欢网球')
        model=Recorder('“我喜欢网球。”')
        bot=Avatar(memory=memory,llm=model,capability_contract_enabled=True,role_state_enabled=True)
        result=bot.respond('原样输出这句话：“我喜欢网球。”')
        assert result['reply']=='我喜欢网球。' and result['generation_mode']=='rules_writing_artifact'
