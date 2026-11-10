"""Explicit read-only health probes. Never generate a reply or send QQ messages."""
from __future__ import annotations
import asyncio
import json
from pathlib import Path
import urllib.request
from urllib.parse import urlsplit


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def model_health(config):
    try:
        url = urlsplit(config.base_url)
    except ValueError:
        return {'ready': False, 'reason': 'invalid_endpoint'}
    if (url.scheme not in ('http', 'https') or url.hostname not in ('127.0.0.1', '::1', 'localhost')
            or url.username or url.password or url.query or url.fragment):
        return {'ready': False, 'reason': 'local_endpoint_required'}
    if not config.api_key:
        return {'ready': False, 'reason': 'model_unconfigured'}
    request = urllib.request.Request(config.base_url.rstrip('/') + '/models',
                                     headers={'Authorization': 'Bearer ' + config.api_key})
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(request, timeout=5) as response:
            raw = response.read(131073)
        if len(raw) > 131072:
            raise ValueError('Response too large')
        models = json.loads(raw)['data']
        matched = any(m.get('id') == config.model for m in models)
        return {'ready': matched, 'reason': 'ok' if matched else 'model_not_listed'}
    except Exception as exc:
        return {'ready': False, 'reason': type(exc).__name__}


def service_running(root):
    """Probe the existing instance lock, not merely a potentially stale PID."""
    try:
        import fcntl
        with (Path(root) / 'service.lock').open('rb') as file:
            try:
                fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(file.fileno(), fcntl.LOCK_UN)
            return False
    except (ImportError, OSError):
        return None


async def onebot_health(settings):
    try:
        import websockets
        async with websockets.connect(
            settings.url, additional_headers={'Authorization': 'Bearer ' + settings.token},
            open_timeout=5, close_timeout=2, max_size=131072,
        ) as ws:
            data = {}
            for action in ('get_login_info', 'get_status'):
                await ws.send(json.dumps({'action': action, 'params': {}, 'echo': action}))
                async def receive():
                    for _ in range(64):
                        result = json.loads(await ws.recv())
                        if result.get('echo') == action:
                            if result.get('retcode') != 0:
                                raise ValueError('OneBot action failed')
                            return result.get('data') or {}
                    raise ValueError('Too many unrelated events')
                data[action] = await asyncio.wait_for(receive(), timeout=5)
        matches = str(data['get_login_info'].get('user_id')) == settings.account
        online = data['get_status'].get('online') is True
        return {'ready': matches and online, 'account_matches': matches, 'online': online}
    except Exception as exc:
        return {'ready': False, 'reason': type(exc).__name__}


async def health():
    from .onebot_app import Settings
    from ...config import config
    try:
        settings = Settings.environment()
    except ValueError:
        return {'ready': False, 'reason': 'onebot_unconfigured', 'messages_sent': 0}
    qq, model = await asyncio.gather(onebot_health(settings), asyncio.to_thread(model_health, config.llm))
    running = service_running(settings.root)
    return {'ready': qq['ready'] and model['ready'] and running is True,
            'qq': qq, 'model': model, 'avatar_service_running': running,
            'messages_sent': 0, 'model_generation_called': False}
