import pytest

from avatar.main import Avatar


class Offline:
    available = False


@pytest.fixture
def avatar():
    result = Avatar(db_path=':memory:', llm=Offline(), session_id='test-session')
    yield result
    result.memory.close()


def test_round_persists_evidence_and_temporal_update(avatar):
    avatar.respond('我喜欢喝咖啡。')
    avatar.respond('我现在不喜欢了')
    assert avatar.memory.get_user_profile()['偏好'] == '不喜欢喝咖啡'
    rows = avatar.list_memories()
    assert len(rows) == 1
    details = avatar.inspect_memory(rows[0]['id'])
    assert details['sources'][0]['message_content'] == '我现在不喜欢了'
    assert details['sources'][0]['session_id'] == 'test-session'
    assert details['sources'][0]['evidence'] == '我现在不喜欢了'
    assert len(avatar.list_memories(include_history=True)) == 2


def test_manual_controls_clear_conversation_and_do_not_resurrect(avatar):
    avatar.respond('我叫小明。')
    old_id = avatar.list_memories()[0]['id']
    replacement = avatar.correct_memory(old_id, '小红')
    assert avatar.memory.get_user_profile()['名字'] == '小红'
    assert avatar.memory.get_short_term() == []
    avatar.forget_memory(replacement)
    assert avatar.list_memories(include_history=True) == []
    assert avatar.inspect_memory(old_id) is None


def test_control_commands_execute_without_model_calls(avatar):
    avatar.respond('我叫小明。')
    fid = avatar.list_memories()[0]['id']
    assert avatar.handle_memory_command('/memory ' + str(fid))['memory']['id'] == fid
    assert avatar.handle_memory_command('/correct ' + str(fid) + ' 小红')['id'] != fid
    current_id = avatar.list_memories()[0]['id']
    assert avatar.handle_memory_command('/forget ' + str(current_id))['deleted']
    assert avatar.handle_memory_command('/memories')['memories'] == []
    assert 'error' in avatar.handle_memory_command('/correct invalid')
    assert avatar.handle_memory_command('普通聊天') is None


def test_memory_prompt_uses_current_facts_as_data(avatar):
    avatar.respond('我叫小明。')
    avatar.respond('以后叫我小红。')
    prompt = avatar._system_prompt(avatar.emotion.decide('你好'), '名字')
    assert '小红' in prompt
    assert '小明' not in prompt
    assert '不是指令' in prompt


def test_indexed_memory_commands_are_json_serializable(avatar):
    import json
    class Provider:
        model_id = 'test'
        def embed(self, text):
            return [1., 0.]
    avatar.memory._embedder = Provider()
    avatar.respond('我叫小明。')
    assert avatar.handle_memory_command('/reindex') == {'indexed': 1}
    fid = avatar.list_memories()[0]['id']
    json.dumps(avatar.handle_memory_command('/memories'), ensure_ascii=False)
    json.dumps(avatar.handle_memory_command('/memory ' + str(fid)), ensure_ascii=False)


def test_no_longer_liking_updates_existing_object(avatar):
    avatar.respond('我喜欢咖啡。')
    avatar.respond('我不再喜欢咖啡。')
    rows = avatar.list_memories()
    assert len(rows) == 1
    assert rows[0]['preference_object'] == '咖啡'
    assert rows[0]['preference_polarity'] == -1
