"""Shared approved configuration, isolated QQ memory, local-admin-only access."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import sqlite3
from types import SimpleNamespace
from ...brain.admin_store import AdminStore
from ...brain.knowledge import KnowledgeService

from ...conversation.configuration import SharedConfiguration, admin_path, workspace_path, context_root


class Contexts:
    def __init__(self, root=None):
        self.root = Path(root) if root is not None else context_root()

    def path(self, key):
        if not re.fullmatch('[a-f0-9]{64}', key):
            raise ValueError('Invalid QQ context')
        directory = self.root / 'contexts' / key
        path = directory / 'memory.db'
        if ((self.root / 'contexts').is_symlink() or directory.is_symlink() or path.is_symlink() or
                not path.resolve().is_relative_to((self.root / 'contexts').resolve()) or not path.is_file()):
            raise ValueError('QQ context missing')
        return path

    @contextmanager
    def memory(self, key):
        from ...brain.memory import MemoryStore
        memory = MemoryStore(str(self.path(key)), embedder=None)
        try:yield memory
        finally:memory.close()

    def list(self):
        rows = []
        folder = self.root / 'contexts'
        if not folder.is_dir():return rows
        for directory in sorted(folder.iterdir()):
            if len(rows) >= 500:break
            if not re.fullmatch('[a-f0-9]{64}', directory.name):continue
            try:
                path = self.path(directory.name)
                conn = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=1)
                try:
                    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    info = {}
                    if 'qq_context_info' in tables:
                        row = conn.execute('SELECT data FROM qq_context_info WHERE id=1').fetchone()
                        if row:info = json.loads(row[0])
                    rows.append({'context_key': directory.name, 'scope': info,
                                 'updated_at': path.stat().st_mtime})
                finally:conn.close()
            except (ValueError, sqlite3.Error, OSError):continue
        return rows
