import json

from avatar.brain.memory import MemoryStore
from avatar.main import Avatar


class Recorder:
    available = True
    def __init__(self):
        self.calls = []
    def chat(self, messages, temperature=.8, **kwargs):
        self.calls.append(messages)
        return json.dumps({'emotion': {'valence': 0, 'arousal': 0}, 'facts': []}) if temperature == 0 else '继续讨论方案。'


def prepare(memory):
    mid = memory.add_message('user', '这轮方案的代号是青岚，预算500元。', 'a')
    for i in range(12):
        memory.add_message('user', '什么是云？', 'a')
        memory.add_message('assistant', '简短解释。', 'a')
    return mid


def test_source_summary_is_in_prompt_without_extra_model_call():
    memory = MemoryStore(':memory:')
    mid = prepare(memory)
    llm = Recorder()
    avatar = Avatar(memory=memory, llm=llm, session_id='a')
    result = avatar.respond('继续讨论前面的方案。')
    assert mid in [r['message_id'] for r in result['conversation_summary']['items']]
    assert '青岚' in llm.calls[-1][0]['content']
    assert len(llm.calls) == 2
    assert avatar.handle_memory_command('/summary')['summary']['items']
    memory.close()


def test_summary_can_be_disabled_for_fair_baseline():
    memory = MemoryStore(':memory:')
    prepare(memory)
    llm = Recorder()
    avatar = Avatar(memory=memory, llm=llm, session_id='a', summary_enabled=False)
    result = avatar.respond('继续讨论前面的方案。')
    assert result['conversation_summary']['items'] == []
    assert '青岚' not in llm.calls[-1][0]['content']
    memory.close()
