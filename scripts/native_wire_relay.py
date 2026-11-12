"""Owned loopback full-body wire archive. Buffered streaming is not a latency probe."""
from contextlib import AbstractContextManager
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, ProxyHandler, build_opener


def require_loopback(url):
    parsed = urlsplit(url)
    if (parsed.scheme != 'http' or parsed.hostname != '127.0.0.1' or not parsed.port
            or parsed.path != '/v1' or parsed.query or parsed.fragment or parsed.username or parsed.password):
        raise ValueError('Expected explicit owned loopback /v1 provider')
    return url


class NativeWireRelay(AbstractContextManager):
    def __init__(self, upstream, archive, *, actual_native):
        self.upstream = require_loopback(upstream)
        if type(actual_native) is not bool:
            raise ValueError('Explicit actual_native boolean required')
        self.actual_native = actual_native
        self.rows = []
        self.guard = threading.RLock()
        self.stream = Path(archive).open('x')
        self.opener = build_opener(ProxyHandler({}))
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                if self.path != '/v1/chat/completions' or self.headers.get('Authorization') != 'Bearer local-eval-only':
                    self.send_error(403)
                    return
                try:
                    size = int(self.headers.get('Content-Length', ''))
                    if not 0 < size <= 2 * 1024 * 1024:
                        self.send_error(413)
                        return
                    raw = self.rfile.read(size)
                    payload = json.loads(raw)
                    if not isinstance(payload, dict):
                        raise ValueError('JSON object required')
                except (ValueError, UnicodeError):
                    self.send_error(400)
                    return
                start = time.monotonic()
                row = {'request': payload, 'raw_request_json': raw.decode(), 'request_body_sha256': sha256(raw).hexdigest(),
                    'actual_native': owner.actual_native, 'kind': 'cognitive' if payload.get('response_format') else 'generation',
                    'outcome': 'admitted', 'buffered_stream': bool(payload.get('stream'))}
                with owner.guard:
                    row['ordinal'] = len(owner.rows) + 1
                    owner.rows.append(row)
                try:
                    request = Request(owner.upstream + '/chat/completions', data=raw,
                        headers={'Content-Type': 'application/json', 'Authorization': 'Bearer local-eval-only'})
                    try:
                        with owner.opener.open(request, timeout=180) as response:
                            body, status, kind = response.read(), response.status, response.headers.get('Content-Type', 'application/json')
                    except HTTPError as error:
                        body, status, kind = error.read(), error.code, error.headers.get('Content-Type', 'application/json')
                    row.update(http_status=status, raw_http_body=body.decode(), response_body_sha256=sha256(body).hexdigest(), content_type=kind)
                    self.send_response(status)
                    self.send_header('Content-Type', kind)
                    self.send_header('Content-Length', str(len(body)))
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    self.wfile.write(body)
                    self.wfile.flush()
                    row['outcome'] = 'completed'
                except (BrokenPipeError, ConnectionResetError) as error:
                    row.update(outcome='client_disconnected', error=repr(error))
                except BaseException as error:
                    row.update(outcome='failed', error=repr(error))
                    raise
                finally:
                    row['seconds'] = time.monotonic() - start
                    with owner.guard:
                        owner.stream.write(json.dumps(row, ensure_ascii=False) + '\n')
                        owner.stream.flush()

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        # Join owned handlers before closing the archive; never close it under
        # an in-flight response. Upstream calls retain their per-request bound.
        self.server.daemon_threads = False
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.closed = False

    @property
    def url(self):
        return f'http://127.0.0.1:{self.server.server_port}/v1'

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.server.shutdown()
        self.thread.join(10)
        self.server.server_close()
        self.stream.close()
        self.closed = not self.thread.is_alive()
        if not self.closed:
            raise RuntimeError('Owned relay did not stop')


def parse_wire(row):
    if row['http_status'] != 200 or row['outcome'] != 'completed':
        raise ValueError('Native wire request did not complete successfully')
    if row['request'].get('stream'):
        parts, finish, ident, done = [], None, None, False
        for line in row['raw_http_body'].splitlines():
            if not line.startswith('data: '):
                continue
            data = line[6:]
            if data == '[DONE]':
                done = True
                continue
            value = json.loads(data)
            ident = value.get('id', ident)
            for choice in value.get('choices', []):
                parts.append(choice.get('delta', {}).get('content') or '')
                finish = choice.get('finish_reason') or finish
        if not done or finish is None:
            raise ValueError('Incomplete native SSE response')
        return {'id': ident, 'reply': ''.join(parts), 'finish_reason': finish}
    value = json.loads(row['raw_http_body'])
    return {'id': value['id'], 'reply': value['choices'][0]['message']['content'], 'finish_reason': value['choices'][0]['finish_reason']}
