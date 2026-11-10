"""Run explicitly with configured local database and document roots."""
import os
from mcp.server.fastmcp import FastMCP
from .local_tools import search_documents
from .web_search import web_search
from .web_fetch import read_webpage
from .weather import get_weather
from avatar.brain.memory import MemoryStore
from avatar.brain.reminders import ReminderStore

mcp = FastMCP('hhu-avatar-assistant')
mcp.tool()(search_documents)
mcp.tool()(web_search)
mcp.tool()(read_webpage)
mcp.tool()(get_weather)

def _store():
    path = os.getenv('MEMORY_DB_PATH')
    if not path:
        raise ValueError('请显式配置 MEMORY_DB_PATH。')
    memory = MemoryStore(path)
    return memory, ReminderStore(memory)

@mcp.tool()
def list_reminders() -> dict:
    """查询本机提醒。"""
    memory, store = _store()
    try:
        return {'reminders': store.list()}
    finally:
        memory.close()

if __name__ == '__main__':
    mcp.run(transport='stdio')
