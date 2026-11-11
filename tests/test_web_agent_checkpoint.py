from contextlib import asynccontextmanager, closing
import json
from types import SimpleNamespace

import pytest

from avatar.brain.memory import MemoryStore
from avatar.cancellation import CancellationToken, Cancelled
from avatar.main import Avatar
from avatar.tools.web_agent import WebAgent


def tool(ident, query):
    return {'id': ident, 'type': 'function', 'function': {
        'name': 'web_search', 'arguments': json.dumps({'query': query})}}


@pytest.mark.parametrize('stage', ['list', 'tool', 'planner', 'synthesis'])
@pytest.mark.parametrize('change', ['cancel', 'forget'])
def test_default_agent_stops_continuation_after_observed_change(tmp_path, stage, change):
    path = str(tmp_path/'web.db'); token = CancellationToken(); calls = []; planning = []; replies = []
    def alter():
        if change == 'cancel': token.cancel()
        else:
            # Planning/synthesis run on a worker: open this writer on that
            # thread instead of touching the caller's SQLite connection.
            with closing(MemoryStore(path)) as writer: writer.forget(fragment)
    class Session:
        async def list_tools(self):
            if stage == 'list': alter()
            return SimpleNamespace(tools=[SimpleNamespace(name=name) for name in ('web_search', 'read_webpage')])
        async def call_tool(self, name, arguments):
            calls.append((name, arguments))
            if stage == 'tool': alter()
            return SimpleNamespace(isError=False, content=[], structuredContent={'results': []})
    @asynccontextmanager
    async def connect(): yield Session()
    class Engine:
        available = True
        def chat_tools(self, messages, **kwargs):
            planning.append(messages)
            if stage == 'planner': alter()
            return {'content': '普通回复。', 'tool_calls': []} if len(planning) > 1 else {
                'content': None, 'tool_calls': [tool('first', '实验资料')]}
        def chat_web(self, messages, **kwargs):
            replies.append(messages)
            if stage == 'synthesis': alter()
            return '受控工具回复。'
        chat = chat_web
    bot = Avatar(db_path=path, llm=Engine(), web_agent=WebAgent(connect=connect))
    try:
        fragment = bot.memory.remember_user('名字', '待删工具实验名')
        text = '帮我搜索实验资料' if stage == 'planner' else '/search 实验资料'
        with pytest.raises(Cancelled): bot.respond(text, use_web=True, cancel=token)
        assert len(calls) == (0 if stage in ('list', 'planner') else 1)
        assert len(planning) == (1 if stage == 'planner' else 0)
        assert len(replies) == (1 if stage == 'synthesis' else 0)
        assert not bot.memory._conn.execute("SELECT 1 FROM memory_messages WHERE role='assistant'").fetchone()
    finally:
        bot.memory.close()


def test_cancellation_after_first_call_does_not_execute_second_in_same_model_batch():
    token = CancellationToken(); calls = []; planning = []
    class Session:
        async def list_tools(self):
            return SimpleNamespace(tools=[SimpleNamespace(name=name) for name in ('web_search', 'read_webpage')])
        async def call_tool(self, name, arguments):
            calls.append(arguments); token.cancel()
            return SimpleNamespace(isError=False, content=[], structuredContent={'results': []})
    @asynccontextmanager
    async def connect(): yield Session()
    class Engine:
        available = True
        def chat_tools(self, messages, **kwargs):
            planning.append(messages)
            return {'content': '完成。', 'tool_calls': []} if len(planning) > 1 else {
                'content': None, 'tool_calls': [tool('first', '一'), tool('second', '二')]}
        def chat(self, *args, **kwargs): raise AssertionError('no synthesis after cancellation')
    bot = Avatar(db_path=':memory:', llm=Engine(), web_agent=WebAgent(connect=connect))
    try:
        with pytest.raises(Cancelled): bot.respond('帮我搜索两个资料', use_web=True, cancel=token)
        assert calls == [{'query': '一'}] and len(planning) == 1
    finally:
        bot.memory.close()


def test_direct_agent_checkpoint_cancel_is_not_swallowed_as_service_fallback():
    @asynccontextmanager
    async def must_not_connect():
        raise AssertionError('cancel before connect')
        yield
    def stop(): raise Cancelled('explicit guard')
    with pytest.raises(Cancelled, match='explicit guard'):
        WebAgent(connect=must_not_connect).run('/search 实验', checkpoint=stop)


def test_no_model_tool_cancellation_closes_session_without_data_fallback():
    token = CancellationToken(); closed = []; calls = []
    class Session:
        async def list_tools(self):
            return SimpleNamespace(tools=[SimpleNamespace(name=name) for name in ('web_search', 'read_webpage')])
        async def call_tool(self, name, arguments):
            calls.append(name); token.cancel()
            return SimpleNamespace(isError=False, content=[], structuredContent={'results': []})
    @asynccontextmanager
    async def connect():
        try: yield Session()
        finally: closed.append(True)
    with pytest.raises(Cancelled):
        WebAgent(connect=connect).run('/search 实验', checkpoint=token.checkpoint)
    assert calls == ['web_search'] and closed == [True]


@pytest.mark.parametrize('stage', ['planner', 'tool', 'synthesis'])
def test_typed_cancelled_from_backend_is_never_service_or_data_fallback(stage):
    calls = []; closed = []
    class Session:
        async def list_tools(self):
            return SimpleNamespace(tools=[SimpleNamespace(name=name) for name in ('web_search', 'read_webpage')])
        async def call_tool(self, name, arguments):
            calls.append('tool')
            if stage == 'tool': raise Cancelled('backend stopped')
            return SimpleNamespace(isError=False, content=[], structuredContent={'results': []})
    @asynccontextmanager
    async def connect():
        try: yield Session()
        finally: closed.append(True)
    class Engine:
        available = True
        def chat_tools(self, *args, **kwargs):
            calls.append('planner'); raise Cancelled('backend stopped')
        def chat(self, *args, **kwargs):
            calls.append('synthesis'); raise Cancelled('backend stopped')
    text = '帮我搜索实验' if stage == 'planner' else '/search 实验'
    with pytest.raises(Cancelled, match='backend stopped'):
        WebAgent(connect=connect).run(text, Engine())
    assert calls == ({'planner': ['planner'], 'tool': ['tool'], 'synthesis': ['tool', 'synthesis']}[stage])
    assert closed == [True]


def test_no_intent_early_return_checks_after_session_cleanup():
    ended = []
    class Session:
        async def list_tools(self):
            return SimpleNamespace(tools=[SimpleNamespace(name=name) for name in ('web_search', 'read_webpage')])
    @asynccontextmanager
    async def connect():
        try: yield Session()
        finally: ended.append(True)
    def guard():
        if ended: raise Cancelled('changed at cleanup')
    with pytest.raises(Cancelled, match='changed at cleanup'):
        WebAgent(connect=connect).run('普通闲聊', checkpoint=guard)
    assert ended == [True]


def test_injected_agent_can_explicitly_adopt_checkpoint_protocol():
    seen = []
    class Offline:
        available = False
    class Agent:
        def run(self, text, llm, *, checkpoint=None):
            seen.append((text, llm, callable(checkpoint)))
            checkpoint()
            return {'reply': '受控代理回复。', 'sources': [], 'tool_calls': []}
    bot = Avatar(db_path=':memory:', llm=Offline(), web_agent=Agent())
    try:
        assert bot.respond('搜索实验', use_web=True)['reply'] == '受控代理回复。'
        assert seen == [('搜索实验', None, True)]
    finally:
        bot.memory.close()
