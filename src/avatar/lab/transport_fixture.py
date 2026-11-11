"""Controlled HTTP provider for transport experiments; never a quality benchmark."""
from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import select
import socket
import threading
import time
from pathlib import Path


@contextmanager
def controlled_provider(delay=0.04, reply_overrides=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            self.server.started.set()
            if data['messages'][-1]['content'] == 'delay-headers':
                readable, _, _ = select.select([self.connection], [], [], 5)
                if readable and not self.connection.recv(1, socket.MSG_PEEK):
                    self.server.disconnected.set()
                return
            text = ('{"emotion":{"valence":0,"arousal":0},"facts":[]}'
                    if data.get('response_format') else '第一句已经生成。第二句继续说明。第三句完成交付。')
            if not data.get('response_format') and 'fixture-long' in data['messages'][-1]['content']:
                text = (Path(__file__).resolve().parents[3] / 'evals/interaction/long-reply-v1.txt').read_text()
            if not data.get('response_format'):
                for trigger, reply in (reply_overrides or {}).items():
                    if trigger in data['messages'][-1]['content']:
                        text = reply
                        break
            pieces = [text[i:i+4] for i in range(0, len(text), 4)]
            if not data.get('stream'):
                time.sleep(delay * len(pieces))
                body = json.dumps({'id': 'fixture', 'choices': [{'message': {'role': 'assistant', 'content': text}}]}).encode()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/event-stream')
            self.end_headers()
            try:
                for piece in pieces:
                    time.sleep(delay)
                    chunk = {'id': 'fixture', 'object': 'chat.completion.chunk', 'created': 1, 'model': 'fixture',
                             'choices': [{'index': 0, 'delta': {'content': piece}, 'finish_reason': None}]}
                    self.wfile.write(('data: ' + json.dumps(chunk) + '\n\n').encode())
                    self.wfile.flush()
                self.wfile.write(b'data: [DONE]\n\n')
            except (BrokenPipeError, ConnectionResetError):
                self.server.disconnected.set()

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.daemon_threads = True
    server.started, server.disconnected = threading.Event(), threading.Event()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, f'http://127.0.0.1:{server.server_port}/v1'
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
