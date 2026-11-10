from contextlib import asynccontextmanager
import json
from types import SimpleNamespace

from avatar.tools.web_agent import MODEL_TOOLS, WebAgent, _explicit_reminder_intent


def call(name, arguments):
    return {'id': 'call_1', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(arguments)}}


class Session:
    def __init__(self):
        self.calls = []
    async def list_tools(self):
        return SimpleNamespace(tools=[SimpleNamespace(name='web_search'), SimpleNamespace(name='read_webpage')])
    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        data = {'results': [{'title': '官方文档', 'url': 'https://example.com/docs', 'snippet': '真实搜索摘要'}]} if name == 'web_search' else {'url': 'https://example.com/docs', 'title': '官方文档', 'text': '真实网页正文', 'truncated': False}
        return SimpleNamespace(isError=False, structuredContent=data, content=[])


def connector(session):
    @asynccontextmanager
    async def connect():
        yield session
    return connect


class LLM:
    available = True
    def __init__(self, responses):
        self.responses = iter(responses)
        self.messages = []
    def chat_tools(self, messages, **kwargs):
        self.messages.append(messages.copy())
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response
    def chat(self, messages, **kwargs):
        self.messages.append(messages.copy())
        return '根据工具返回的资料，这是官方文档。'


def test_native_call_executes_tool_and_only_cites_returned_sources():
    session = Session()
    llm = LLM([{'role': 'assistant', 'content': None, 'tool_calls': [call('web_search', {'query': 'MCP'})]},
               {'role': 'assistant', 'content': '查到官方文档，https://evil.example/fake', 'tool_calls': []}])
    result = WebAgent(connect=connector(session)).run('帮我搜索MCP文档', llm)
    assert session.calls == [('web_search', {'query': 'MCP'})]
    assert result['sources'][0]['url'] == 'https://example.com/docs'
    assert 'evil.example' not in result['reply']
    assert result['tool_calls'][0]['routing'] == 'model'
    assert llm.messages[-1][-1]['role'] == 'tool'


def test_repeated_calls_are_bounded_and_not_executed_again():
    session = Session()
    message = {'role': 'assistant', 'content': None, 'tool_calls': [call('web_search', {'query': 'MCP'})]}
    result = WebAgent(connect=connector(session), max_calls=3).run('搜索MCP', LLM([message] * 4))
    assert len(session.calls) == 1
    assert len(result['tool_calls']) <= 3
    assert any(r['status'] == 'rejected' for r in result['tool_calls'])


def test_bad_arguments_cannot_reach_mcp_server():
    session = Session()
    llm = LLM([{'role': 'assistant', 'content': None, 'tool_calls': [call('web_search', {'query': 'MCP', 'command': 'delete'})]},
               {'role': 'assistant', 'content': '我已经搜索成功。'}])
    result = WebAgent(connect=connector(session)).run('帮我查MCP', llm)
    assert session.calls == []
    assert result['sources'] == []
    assert '没有成功' in result['reply']


def test_unsupported_native_tools_falls_back_to_explicit_user_search():
    session = Session()
    result = WebAgent(connect=connector(session)).run('帮我搜索MCP官方文档', LLM([RuntimeError('unsupported tools')]))
    assert len(session.calls) == 1
    assert result['tool_calls'][0]['routing'] == 'fallback'
    assert result['sources']


def test_explicit_read_works_without_model_and_no_private_context_is_needed():
    session = Session()
    result = WebAgent(connect=connector(session)).run('/read https://example.com/docs', None)
    assert session.calls == [('read_webpage', {'url': 'https://example.com/docs'})]
    assert '真实网页正文' in result['reply']
    assert result['tool_calls'][0]['routing'] == 'explicit'


def test_known_markdown_citation_is_not_mangled_as_unverified():
    session = Session()
    llm = LLM([{'role': 'assistant', 'tool_calls': [call('web_search', {'query': 'MCP'})]},
               {'role': 'assistant', 'content': '官方文档：[https://example.com/docs](https://example.com/docs)，介绍MCP SDK。'}])
    result = WebAgent(connect=connector(session)).run('搜索MCP', llm)
    assert '未验证链接' not in result['reply']
    assert 'MCP SDK' in result['reply']
    assert 'https://example.com/docs' in result['reply']


def test_weather_intent_uses_unified_tool_without_llm():
    class WeatherSession(Session):
        async def list_tools(self):
            return SimpleNamespace(tools=[SimpleNamespace(name=name) for name in
                ('web_search', 'read_webpage', 'get_weather')])
        async def call_tool(self, name, arguments):
            self.calls.append((name, arguments))
            return SimpleNamespace(isError=False, structuredContent={
                'location': '南京, 中国', 'current': {'temperature_2m': 19, 'weather': '多云'},
                'forecast': [], 'provider': 'open-meteo'}, content=[])
    session = WeatherSession()
    result = WebAgent(connect=connector(session)).run('查一下南京天气', None)
    assert session.calls == [('get_weather', {'location': '南京'})]
    assert '19' in result['reply']
    assert result['tool_calls'][0]['status'] == 'ok'


def test_reminder_write_rejects_non_explicit_text_before_mcp():
    session = Session()
    llm = LLM([{'role': 'assistant', 'content': None,
                'tool_calls': [call('create_reminder', {'text': '明天下午3点答辩'})]},
               {'role': 'assistant', 'content': '完成'}])
    result = WebAgent(connect=connector(session)).run('我明天下午3点答辩', llm)
    assert session.calls == []
    assert result['tool_calls'][0]['status'] == 'rejected'

def test_model_never_receives_reminder_write_tools():
    assert not {'create_reminder', 'cancel_reminder'} & {
        tool['function']['name'] for tool in MODEL_TOOLS
    }

def test_reminder_mutation_requires_exact_explicit_command():
    assert _explicit_reminder_intent('提醒我2099年12月1日下午3点答辩') == (
        'create_reminder', {'text': '提醒我2099年12月1日下午3点答辩'})
    assert _explicit_reminder_intent('请取消提醒编号12。') == (
        'cancel_reminder', {'reminder_id': 12})
    assert _explicit_reminder_intent('搜索网页，并顺便帮我处理提醒') is None
