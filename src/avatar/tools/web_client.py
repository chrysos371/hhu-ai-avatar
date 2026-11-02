"""One MCP stdio session per user tool chain, with a minimal child environment."""
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
import os
import sys

from .web_fetch import system_proxy


@asynccontextmanager
async def web_session():
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError:
        raise RuntimeError('请先安装 requirements-web.txt 中的 MCP 扩展。') from None
    src = Path(__file__).resolve().parents[2]
    env = {'PYTHONPATH': str(src), 'PYTHONIOENCODING': 'utf-8', 'PYTHON_DOTENV_DISABLED': '1'}
    proxy = system_proxy()
    if proxy:
        env['AVATAR_WEB_PROXY'] = proxy
    params = StdioServerParameters(command=sys.executable, args=['-u', '-m', 'avatar.tools.web_server'], env=env, cwd=str(src.parent))
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=35)) as session:
            await session.initialize()
            yield session


@asynccontextmanager
async def assistant_session(memory_db_path: str, document_roots: str = ''):
    """Start the complete assistant tool server with an explicit minimal environment."""
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError:
        raise RuntimeError('请先安装 requirements-web.txt 中的 MCP 扩展。') from None
    src = Path(__file__).resolve().parents[2]
    env = {'PYTHONPATH': str(src), 'PYTHONIOENCODING': 'utf-8', 'PYTHON_DOTENV_DISABLED': '1',
           'MEMORY_DB_PATH': str(Path(memory_db_path).resolve())}
    if document_roots:
        env['AVATAR_DOCUMENT_ROOTS'] = document_roots
    proxy = system_proxy()
    if proxy:
        env['AVATAR_WEB_PROXY'] = proxy
    params = StdioServerParameters(command=sys.executable, args=['-u', '-m', 'avatar.tools.assistant_server'],
                                   env=env, cwd=str(src.parent))
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=35)) as session:
            await session.initialize()
            yield session
