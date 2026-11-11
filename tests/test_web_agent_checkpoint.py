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
