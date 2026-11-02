"""Longer backend scenarios with real SQLite; no remote model or production data."""
from avatar.main import Avatar


class Offline:
    available = False


def test_preferences_and_sources_across_sessions_then_delete(tmp_path):
    db = str(tmp_path / 'dialogue.db')
    first = Avatar(db_path=db, llm=Offline(), session_id='first')
    first.respond('我叫阿岚，我喜欢喝咖啡，我讨厌香菜。')
    first.respond('我现在不喜欢咖啡了。')
    first.respond('以后叫我小岚。')
    first.memory.close()
    second = Avatar(db_path=db, llm=Offline(), session_id='second')
    second.respond('假如我叫小红，你会怎么介绍我？')
    second.respond('你还记得我的名字吗？')
    profile = second.memory.get_user_profile()
    assert profile['名字'] == '小岚'
    assert set(profile['偏好'].split('；')) == {'不喜欢咖啡', '讨厌香菜'}
    current_name = next(row for row in second.list_memories() if row['profile_key'] == '名字')
    assert second.inspect_memory(current_name['id'])['sources'][0]['session_id'] == 'first'
    second.forget_memory(current_name['id'])
    assert '名字' not in second.memory.get_user_profile()
    assert not any('阿岚' in row['content'] or '小岚' in row['content']
                   for row in second.list_memories(include_history=True))
    assert second.memory.get_short_term() == []
    second.memory.close()


def test_uncertain_reference_does_not_change_multiple_preferences():
    avatar = Avatar(db_path=':memory:', llm=Offline())
    avatar.respond('我喜欢咖啡，我喜欢茶。')
    avatar.respond('我现在不喜欢了。')
    assert set(avatar.memory.get_user_profile()['偏好'].split('；')) == {'喜欢咖啡', '喜欢茶'}
    avatar.memory.close()


def test_distress_to_practical_help_to_celebration():
    avatar = Avatar(db_path=':memory:', llm=Offline())
    sad = avatar.respond('考试没过，我很难过，但暂时不想听建议。')
    assert sad['strategy'] == 'listen'
    assert sad['user_valence'] < 0
    assert sad['valence'] >= 0
    practical = avatar.respond('别安慰我了，帮我分析一下怎么复习。')
    assert practical['strategy'] == 'advise'
    happy = avatar.respond('刚查到成绩改正了，我及格啦！')
    assert happy['strategy'] == 'celebrate'
    assert happy['user_valence'] > 0
    avatar.memory.close()


def test_long_conversation_cannot_resurrect_removed_memory():
    avatar = Avatar(db_path=':memory:', llm=Offline())
    avatar.respond('我叫林舟。')
    fid = avatar.list_memories()[0]['id']
    avatar.correct_memory(fid, '小林')
    avatar.forget_memory(fid)
    for index in range(25):
        avatar.respond(f'今天聊第{index}个普通话题。')
    assert avatar.list_memories(include_history=True) == []
    assert not any('林舟' in m['content'] or '小林' in m['content']
                   for m in avatar.memory.get_short_term())
    avatar.memory.close()
