import asyncio
import json
from contextlib import asynccontextmanager

from avatar.tools.web_client import assistant_session


def _data(result):
    assert not result.isError
    if result.structuredContent is not None:
        return result.structuredContent
    return json.loads('\n'.join(block.text for block in result.content))


def test_assistant_mcp_document_and_reminder_lifecycle(tmp_path):
    (tmp_path / 'course.md').write_text('水文学课程包含降雨径流分析。', encoding='utf-8')

    async def scenario():
        async with assistant_session(str(tmp_path / 'memory.db'), str(tmp_path)) as session:
            names = {tool.name for tool in (await session.list_tools()).tools}
            assert names == {'web_search', 'read_webpage', 'get_weather', 'search_documents',
                             'list_reminders', 'create_reminder', 'cancel_reminder'}
            docs = _data(await session.call_tool('search_documents', {'query': '降雨'}))
            assert docs['results'][0]['path'] == 'course.md'
            created = _data(await session.call_tool(
                'create_reminder', {'text': '提醒我2099年12月1日下午3点答辩'}))
            reminder_id = created['reminder']['id']
            listed = _data(await session.call_tool('list_reminders', {}))
            assert listed['reminders'][0]['id'] == reminder_id
            _data(await session.call_tool('cancel_reminder', {'reminder_id': reminder_id}))
            listed = _data(await session.call_tool('list_reminders', {}))
            assert listed['reminders'][0]['status'] == 'cancelled'

    # Windows/Python 3.14 subprocess startup and first SQLite import can take
    # several seconds in CI; individual MCP calls still keep their 35s limit.
    asyncio.run(asyncio.wait_for(scenario(), timeout=90))
