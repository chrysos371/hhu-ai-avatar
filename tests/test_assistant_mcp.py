import asyncio
import json
from contextlib import asynccontextmanager

from avatar.tools.web_client import assistant_session


def _data(result):
    assert not result.isError
    if result.structuredContent is not None:
        return result.structuredContent
    return json.loads('\n'.join(block.text for block in result.content))


def test_assistant_mcp_is_read_only_for_reminders(tmp_path):
    (tmp_path / 'course.md').write_text('水文学课程包含降雨径流分析。', encoding='utf-8')

    async def scenario():
        async with assistant_session(str(tmp_path / 'memory.db'), str(tmp_path)) as session:
            names = {tool.name for tool in (await session.list_tools()).tools}
            assert names == {'web_search', 'read_webpage', 'get_weather', 'search_documents',
                             'list_reminders'}
            docs = _data(await session.call_tool('search_documents', {'query': '降雨'}))
            assert docs['results'][0]['path'] == 'course.md'
            listed = _data(await session.call_tool('list_reminders', {}))
            assert listed['reminders'] == []

    # Windows/Python 3.14 subprocess startup and first SQLite import can take
    # several seconds in CI; individual MCP calls still keep their 35s limit.
    asyncio.run(asyncio.wait_for(scenario(), timeout=90))
