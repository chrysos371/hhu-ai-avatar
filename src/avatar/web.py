"""Single-user loopback management UI. Run: python -m avatar.web."""
from __future__ import annotations

import argparse
import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from urllib.parse import parse_qs, urlsplit

from .brain.emotion import EmotionEngine
from .brain.boundaries import BoundaryPolicy
from .brain.memory import MemoryStore
from .brain.reminders import ReminderStore
from .brain.summaries import SummaryStore
from .web_ui import PAGE


def _public(row):
    return {k: v for k, v in row.items() if k != 'content_vector'} if row is not None else None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status, data, *, html=False):
        body = data.encode('utf-8') if html else json.dumps(data, ensure_ascii=False, allow_nan=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8' if html else 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'none'; script-src 'nonce-" + self.server.nonce + "'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def _request(self, post=False):
        expected_host = f'127.0.0.1:{self.server.server_port}'
        if self.headers.get('Host') != expected_host:
            return self._send(403, {'error': 'invalid host'})
        origin = self.headers.get('Origin')
        if origin and origin != 'http://' + expected_host:
            return self._send(403, {'error': 'invalid origin'})
        parsed = urlsplit(self.path)
        if not post and parsed.path == '/':
            return self._send(200, PAGE.replace('__NONCE__', self.server.nonce), html=True)
        if not parsed.path.startswith('/api/'):
            return self._send(404, {'error': 'not found'})
        token = self.headers.get('X-Avatar-Token', '')
        if not secrets.compare_digest(token.encode(), self.server.token.encode()):
            return self._send(403, {'error': '请使用启动终端提供的完整链接打开页面。'})
        memory = None
        try:
            data = {}
            if post:
                if self.headers.get_content_type() != 'application/json':
                    raise ValueError('Content-Type must be application/json')
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 16384:
                    raise ValueError('request body must be 1..16384 bytes')
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError('JSON object required')
            def ident():
                value = data.get('id')
                if type(value) is not int or value <= 0:
                    raise ValueError('positive integer id required')
                return value
            def text(field):
                value = data.get(field)
                if not isinstance(value, str) or not value.strip() or len(value) > 4000:
                    raise ValueError('non-empty text up to 4000 characters required')
                return value.strip()
            path = parsed.path
            if post and path == '/api/chat':
                from .main import Avatar
                user_text = text('text')
                use_web = data.get('use_web', False)
                if type(use_web) is not bool:
                    raise ValueError('use_web must be boolean')
                with self.server.state_lock:
                    avatar = Avatar(db_path=self.server.db_path, session_id=self.server.session_id)
                    memory = avatar.memory
                    avatar.emotion = self.server.emotion
                    avatar.boundaries = self.server.boundaries
                    if self.server.context_revision != memory.context_revision:
                        self.server.short_term = []
                    for message in self.server.short_term:
                        memory.add_short_term(message['role'], message['content'])
                    result = avatar.respond(user_text, use_web=use_web)
                    self.server.short_term = memory.get_short_term()
                    self.server.context_revision = memory.context_revision
                return self._send(200, result)
            memory = MemoryStore(self.server.db_path)
            reminders = ReminderStore(memory)
            query = parse_qs(parsed.query)
            if not post and path == '/api/memories':
                result = {'memories': [_public(row) | {'strength': memory.memory_strength(row)}
                                      for row in memory.list_memories(include_history=query.get('history') == ['1'], limit=5000)]}
            elif not post and path == '/api/memory':
                result = {'memory': _public(memory.inspect(int(query.get('id', ['0'])[0])))}
            elif not post and path == '/api/reminders':
                result = {'reminders': reminders.list()}
            elif not post and path == '/api/summary':
                result = {'summary': SummaryStore(memory).read(self.server.session_id)}
            elif not post and path == '/api/state':
                with self.server.state_lock:
                    state = self.server.emotion.state
                    result = {'energy': self.server.emotion.energy, 'valence': state.valence,
                              'arousal': state.arousal, 'mode': '单用户本机模式'}
            elif post and path == '/api/correct':
                result = {'id': memory.correct(ident(), text('content'))}
                with self.server.state_lock:
                    self.server.short_term = []
            elif post and path == '/api/forget':
                memory.forget(ident())
                with self.server.state_lock:
                    self.server.short_term = []
                result = {'ok': True}
            elif post and path == '/api/forget-summary-source':
                SummaryStore(memory).forget_source(self.server.session_id, ident())
                with self.server.state_lock:
                    self.server.short_term = []
                result = {'ok': True}
            elif post and path == '/api/badhit':
                memory.report_irrelevant(ident())
                result = {'ok': True}
            elif post and path == '/api/reminders':
                result = {'reminder': reminders.create(text('text'))}
            elif post and path == '/api/reminder-status':
                reminders.set_status(ident(), text('status'))
                result = {'ok': True}
            elif post and path == '/api/delete-reminder':
                reminders.delete(ident())
                result = {'ok': True}
            elif post and path == '/api/due':
                result = {'reminders': reminders.claim_due()}
            else:
                return self._send(404, {'error': 'not found'})
            self._send(200, result)
        except (ValueError, TypeError, UnicodeError) as exc:
            self._send(400, {'error': str(exc)})
        except Exception:
            self._send(500, {'error': '操作失败，请检查数据库或模型服务。'})
        finally:
            if memory is not None:
                memory.close()

    def do_GET(self):
        self._request()

    def do_POST(self):
        self._request(post=True)


def create_server(db_path: str, *, port: int = 8765) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    server.db_path = db_path
    server.token = secrets.token_urlsafe(32)
    server.nonce = secrets.token_urlsafe(24)
    server.session_id = secrets.token_hex(16)
    server.short_term = []
    server.context_revision = None
    server.emotion = EmotionEngine()
    server.boundaries = BoundaryPolicy()
    server.state_lock = threading.RLock()
    return server


def main():
    from .config import config
    parser = argparse.ArgumentParser(description='Avatar 单用户本机管理页面')
    parser.add_argument('--db', default=config.memory_db_path)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    server = create_server(args.db, port=args.port)
    print(f'本机管理页面：http://127.0.0.1:{server.server_port}/#{server.token}', flush=True)
    print('保持程序和页面运行以轮询提醒；当前为单用户模式。Ctrl+C 退出。', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
