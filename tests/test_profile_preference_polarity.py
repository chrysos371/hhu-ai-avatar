"""Both preference polarities retain user ownership and verified history."""
from contextlib import closing

import pytest

from avatar.brain.memory import MemoryStore
from avatar.main import Avatar
from test_capability_prompt_lab import Recorder
from avatar.brain.profile_grounding import review_profile_reply


@pytest.mark.parametrize('value',['喜欢网球','不喜欢网球','不爱咖啡','讨厌芹菜','爱科幻'])
def test_copied_current_user_preference_and_its_recovered_reply_keep_the_same_owner(tmp_path,value):
    db=str(tmp_path/'polarity.db')
    with closing(MemoryStore(db)) as memory:
        memory.remember_user('偏好',value)
        model=Recorder('我'+value+'。');pieces=[]
        bot=Avatar(memory=memory,llm=model,capability_contract_enabled=True,role_state_enabled=True)
        first=bot.respond('今天聊聊。',on_delta=pieces.append)
        assert first['generation_mode']=='rules_profile_source'
        assert first['reply']=='目前关于你的偏好记录是：'+value+'。'
        assert not pieces or ''.join(pieces)==first['reply']
    with closing(MemoryStore(db)) as memory:
        model=Recorder('普通回复。')
        bot=Avatar(memory=memory,llm=model,capability_contract_enabled=True,role_state_enabled=True)
        bot.respond('换个话题。')
        assert any(m['role']=='assistant' and 'rules_profile_source' in m['content']
            and first['reply'] in m['content'] for m in model.native[-1])


@pytest.mark.parametrize('value',['不喜欢网球','不爱咖啡','讨厌芹菜'])
def test_requested_character_quote_is_preserved_instead_of_becoming_user_profile_reply(value):
    with closing(MemoryStore(':memory:')) as memory:
        memory.remember_user('偏好',value)
        bot=Avatar(memory=memory,llm=Recorder('不应生成'),capability_contract_enabled=True,role_state_enabled=True)
        result=bot.respond('原样输出这句小说台词：“我'+value+'。”')
        assert result['generation_mode']=='rules_writing_artifact' and result['reply']=='我'+value+'。'


@pytest.mark.parametrize('source,reply',[
    ('不喜欢网球','我不喜欢网球比赛。'),
    ('喜欢网球','我不喜欢网球。'),
    ('不喜欢网球','我喜欢网球。'),
    ('讨厌芹菜','“我讨厌芹菜。”'),
])
def test_different_objects_polarities_and_quoted_data_are_not_claimed_to_be_a_copy(source,reply):
    assert review_profile_reply('今天聊聊。',reply,{'偏好':source})==(reply,None)
