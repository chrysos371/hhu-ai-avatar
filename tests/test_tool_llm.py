from types import SimpleNamespace

from avatar.brain.llm import LLMEngine


def test_native_tool_response_preserves_tool_calls_and_ids():
    captured = {}
    data = {'role': 'assistant', 'content': None, 'tool_calls': [
        {'id': 'call_123', 'type': 'function', 'function': {'name': 'web_search', 'arguments': '{"query":"MCP"}'}}]}
    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(model_dump=lambda **_: data))])
    engine = LLMEngine(api_key='test', base_url='http://localhost:11434/v1')
    engine._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    schemas = [{'type': 'function', 'function': {'name': 'web_search'}}]
    result = engine.chat_tools([{'role': 'user', 'content': '查MCP'}], tools=schemas)
    assert result['tool_calls'][0]['id'] == 'call_123'
    assert captured['tools'] == schemas
    assert captured['messages'][0]['content'] == '查MCP'
