"""Reached exclusively through the authenticated loopback management API."""
import json
import re
import sqlite3
from .management import Contexts
from ...brain.operations import OperationError


def handle(server, post, path, query, data):
    contexts = Contexts()
    if path == '/qq/contexts' and not post:
        return 200, contexts.list()
    match = re.fullmatch(r'/qq/contexts/([a-f0-9]{64})(/.*)', path)
    if not match:
        raise OperationError(404, 'qq_context_not_found')
    key, route = match.groups()
    get_allowed = (route in ('/memory', '/audit', '/traces') or
                   re.fullmatch(r'/(?:memory|operations)/\d+', route))
    post_allowed = (route == '/memory/batch-draft' or
                    re.fullmatch(r'/operations/\d+/confirm', route) or
                    re.fullmatch(r'/audit/\d+/reverse-draft', route))
    if (post and not post_allowed) or (not post and not get_allowed):
        raise OperationError(403, 'qq_management_route_forbidden')
    if route == '/memory/batch-draft':
        actions = data.get('actions')
        if not isinstance(actions, list) or any(not isinstance(a, dict) or a.get('action') not in ('correct','forget','badhit') for a in actions):
            raise OperationError(422, 'qq_memory_actions_only')
    try:
        with contexts.memory(key) as memory:
            if route == '/traces':
                exists = memory._conn.execute("SELECT 1 FROM sqlite_master WHERE name='qq_turn_traces'").fetchone()
                rows = memory._conn.execute('SELECT receipt_key,created_at,data FROM qq_turn_traces ORDER BY created_at DESC LIMIT 50').fetchall() if exists else []
                return 200, [{'receipt_key': r['receipt_key'], 'created_at': r['created_at'],
                              'trace': json.loads(r['data'])} for r in rows]
            from ...web_api import V1API
            return V1API(server, memory, None).handle(post, route, query, data)
    except ValueError:
        raise OperationError(404, 'qq_context_not_found') from None
    except sqlite3.OperationalError:
        raise OperationError(409, 'qq_context_busy', '该 QQ 会话正在处理消息，请稍后重试。') from None
