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

@mcp.tool()
def create_reminder(text: str) -> dict:
    """仅在用户明确要求创建时调用；原文必须以提醒我开头且含日期钟点事项。"""
    memory, store = _store()
    try:
        return {'reminder': store.create(text)}
    finally:
        memory.close()

@mcp.tool()
def cancel_reminder(reminder_id: int) -> dict:
    """按查询所得编号取消用户明确指定的提醒。"""
    if type(reminder_id) is not int or reminder_id < 1:
        raise ValueError('提醒编号无效。')
    memory, store = _store()
    try:
        store.set_status(reminder_id, 'cancelled')
        return {'id': reminder_id, 'status': 'cancelled'}
    finally:
        memory.close()

if __name__ == '__main__':
    mcp.run(transport='stdio')
