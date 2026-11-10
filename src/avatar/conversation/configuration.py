"""Shared approved configuration, isolated QQ memory, local-admin-only access."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import sqlite3
from types import SimpleNamespace
from ..brain.admin_store import AdminStore
from ..brain.knowledge import KnowledgeService

PROJECT = Path(__file__).resolve().parents[3]


def workspace_path(value):
    path = Path(value).resolve()
    if not path.is_relative_to(PROJECT.parent):
        raise ValueError('QQ management paths must stay in workspace')
    return path


def admin_path():
    from ..config import config
    return workspace_path(os.getenv('AVATAR_QQ_ADMIN_DB', config.memory_db_path))


def context_root():
    return workspace_path(os.getenv('AVATAR_ONEBOT_STATE_DIR', str(PROJECT / 'data/qq-onebot')))


class SharedConfiguration:
    """Materialize only approved persona and relevant public knowledge; no user memory."""
    def __init__(self, path, query):
        self.persona = None
        self.knowledge = []
        self.degraded = False
        path = Path(path)
        self.path = path
        if not path.is_file():
            self.degraded = True
            return
        try:
            conn = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, timeout=2)
        except sqlite3.Error:
            self.degraded = True
            return
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('BEGIN')
            store = AdminStore(SimpleNamespace(_conn=conn, _embedder=None))
            self.persona = store.current_persona()
            if query.strip():
                self.knowledge = KnowledgeService(store).search(query[:200], limit=3)
        except (sqlite3.Error, ValueError, TypeError):
            self.degraded = True
            self.persona = None
            self.knowledge = []
        finally:
            conn.close()

    def current_persona(self):
        return self.persona
