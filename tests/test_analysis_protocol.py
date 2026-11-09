import json
from types import SimpleNamespace

from avatar.brain.analysis_protocol import ANALYSIS_RESPONSE_FORMAT
from avatar.brain.llm import LLMEngine
from avatar.main import Avatar


def test_llm_analysis_requests_schema_but_normal_chat_does_not():
    requests = []
    def create(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            content='{"emotion":{"valence":0,"arousal":0},"facts":[]}'))])
    engine = LLMEngine(api_key='test')
    engine._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    engine.chat_analysis([{'role': 'user', 'content': '你好'}])
    engine.chat([{'role': 'user', 'content': '你好'}])
    assert requests[0]['response_format'] == ANALYSIS_RESPONSE_FORMAT
    assert 'response_format' not in requests[1]


def test_avatar_uses_analysis_capability_separately_from_reply(tmp_path):
    class Model:
        available = True
        def __init__(self):
            self.analysis_calls = 0
            self.reply_calls = 0
        def chat_analysis(self, messages, temperature=0):
            self.analysis_calls += 1
            return json.dumps({'emotion': {'valence': 0, 'arousal': 0}, 'facts': []})
        def chat(self, messages, **kwargs):
            self.reply_calls += 1
            return '收到。'
    model = Model()
    avatar = Avatar(db_path=str(tmp_path / 'memory.db'), llm=model)
    try:
        avatar.respond('我喜欢游泳，也喜欢骑车。')
        assert {r['content'] for r in avatar.list_memories()} == {'偏好: 喜欢游泳', '偏好: 喜欢骑车'}
        avatar.respond('现在我不喜欢游泳了。')
        active = {r['content'] for r in avatar.list_memories()}
        assert active == {'偏好: 不喜欢游泳', '偏好: 喜欢骑车'}
        assert any(r['content'] == '偏好: 喜欢游泳' for r in avatar.list_memories(include_history=True))
        assert model.analysis_calls == model.reply_calls == 2
    finally:
        avatar.memory.close()
