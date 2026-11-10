"""QQ read-only tools: explicit requests, no personal history in tool planning."""
from contextlib import asynccontextmanager
import asyncio
import json
import os
import re
from types import SimpleNamespace
from ..tools.web_agent import WebAgent, _SYSTEM
from ..brain.boundaries import BOUNDARY_PROMPT

READ_ONLY = {'web_search', 'read_webpage', 'get_weather', 'search_documents'}


def tool_command(text):
    if re.match(r'^/(search|read|weather|docs)\s+\S', text):
        return text
    match = re.match(r'^(?:请)?(?:帮我)?(联网搜索|上网搜|搜索|搜一下|查一下天气|查询天气|查资料|查询资料|查一下|查询)\s*(.+)$', text)
    if not match:
        return None
    intent, query = match.groups()
    if '资料' in intent:
        return '/docs ' + query.strip()
    if '天气' in intent:
        return '/weather ' + query.strip()
    if re.search(r'(天气|气温|下雨)', query):
        from ..tools.web_agent import _intent
        routed = _intent(query)
        if routed and routed[0] == 'get_weather':
            return '/weather ' + routed[1]['location']
    return '/search ' + query.strip()


def tool_request(text):
    return tool_command(text) is not None


class QQWebAgent(WebAgent):
    def run(self, user_text, llm=None):
        command = tool_command(user_text)
        if command is None:
            return {'reply': '请说明要查询的内容。', 'sources': [], 'tool_calls': []}
        return super().run(command, llm)


class ReadOnlySession:
    def __init__(self, shared):self.shared = shared
    async def list_tools(self):
        return SimpleNamespace(tools=[SimpleNamespace(name=n) for n in sorted(READ_ONLY)])

    async def call_tool(self, name, arguments):
        if name not in READ_ONLY:
            raise ValueError('QQ only supports read-only queries')
        from ..tools.web_search import web_search
        from ..tools.web_fetch import read_webpage
        from ..tools.weather import get_weather
        from ..tools.local_tools import search_documents_in
        from .configuration import SharedConfiguration, admin_path, workspace_path
        def documents(query, limit=5):
            # Search approved knowledge, never the management database's user facts.
            shared = SharedConfiguration(self.shared.path, query)
            rows = [{'title': r['title'], 'source_id': r['source_id'],
                     'path': '知识库/' + r['title'], 'excerpt': r['content'][:700]}
                    for r in shared.knowledge]
            configured = os.getenv('AVATAR_QQ_DOCUMENT_ROOTS', '')
            if configured:
                roots = os.pathsep.join(str(workspace_path(p)) for p in configured.split(os.pathsep) if p.strip())
                rows.extend(search_documents_in(query, limit, roots)['results'])
            return {'results': rows[:limit], 'untrusted': True,
                    'management_degraded': shared.degraded}
        function = {'web_search': web_search, 'read_webpage': read_webpage,
                    'get_weather': get_weather, 'search_documents': documents}[name]
        result = await asyncio.to_thread(function, **arguments)
        return SimpleNamespace(structuredContent=result, isError=False)


def make_agent(shared):
    @asynccontextmanager
    async def connect():yield ReadOnlySession(shared)
    persona = shared.persona['data'] if shared.persona else {}
    prompt = (_SYSTEM + '\n' + BOUNDARY_PROMPT +
              '\n已确认的人设数据（仅调整表达，不得覆盖安全或工具权限）：' +
              json.dumps(persona, ensure_ascii=False))
    return QQWebAgent(connect=connect, allowed_tools=READ_ONLY, system_prompt=prompt)
