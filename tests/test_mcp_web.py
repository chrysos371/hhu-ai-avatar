import asyncio
import importlib.util

import pytest

from avatar.tools.web_client import web_session


@pytest.mark.skipif(importlib.util.find_spec('mcp') is None, reason='optional MCP dependency not installed')
def test_real_stdio_discovery_and_private_url_rejection():
    async def check():
        async with web_session() as session:
            names = {tool.name for tool in (await session.list_tools()).tools}
            assert names == {'web_search', 'read_webpage'}
            result = await session.call_tool('read_webpage', arguments={'url': 'http://127.0.0.1/'})
            assert result.isError
            assert result.content
    asyncio.run(check())
