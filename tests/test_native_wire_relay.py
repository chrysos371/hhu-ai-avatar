"""Actual HTTP wire preservation and request admission; no GPU/model required."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from hashlib import sha256
import json
from pathlib import Path
import sys
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from native_wire_relay import NativeWireRelay, parse_wire, require_loopback
@contextmanager
def complete_provider(delay=0, error_status=200):
    del delay
    text = '第一句已经生成。第二句继续说明。第三句完成交付。'
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def do_POST(self):
            self.server.started.set()
            data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if error_status != 200:
                body = json.dumps({'error': {'message': 'controlled unavailable'}}).encode()
                kind = 'application/json'
            elif data.get('stream'):
                chunks = [{'id': 'complete-fixture', 'choices': [{'delta': {'content': text}, 'finish_reason': None}]},
                          {'id': 'complete-fixture', 'choices': [{'delta': {}, 'finish_reason': 'stop'}]}]
                body = (''.join('data: ' + json.dumps(c, ensure_ascii=False) + '\n\n' for c in chunks) + 'data: [DONE]\n\n').encode()
                kind = 'text/event-stream'
            else:
                body = json.dumps({'id': 'complete-fixture', 'choices': [{'message': {'content': text}, 'finish_reason': 'stop'}]}, ensure_ascii=False).encode()
                kind = 'application/json'
            self.send_response(error_status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    server.started = threading.Event()
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield server, f'http://127.0.0.1:{server.server_port}/v1'
    finally:
        server.shutdown()
        worker.join(10)
        server.server_close()


@pytest.mark.parametrize('stream', [False, True])
def test_real_http_preserves_exact_request_and_response_and_closes_archive(tmp_path, stream):
    payload = {'messages': [{'role': 'user', 'content': '  原样空格与中文  '}], 'stream': stream, 'temperature': 0}
    # Noncanonical whitespace is intentional: hashing a reserialized dict would fail.
    raw = json.dumps(payload, ensure_ascii=False, indent=2).encode()
    archive = tmp_path / 'wire.jsonl'
    with complete_provider(delay=0) as (_, url):
        with NativeWireRelay(url, archive, actual_native=False) as relay:
            request = Request(relay.url + '/chat/completions', data=raw,
                headers={'Authorization': 'Bearer local-eval-only', 'Content-Type': 'application/json'})
            with build_opener(ProxyHandler({})).open(request, timeout=10) as response:
                body = response.read()
        assert relay.closed
    row = json.loads(archive.read_text())
    assert row['raw_request_json'].encode() == raw and row['request_body_sha256'] == sha256(raw).hexdigest()
    assert row['raw_http_body'].encode() == body and row['response_body_sha256'] == sha256(body).hexdigest()
    assert row['actual_native'] is False and row['buffered_stream'] == stream
    parsed = parse_wire(row)
    assert parsed['finish_reason'] == 'stop' and parsed['reply'] == '第一句已经生成。第二句继续说明。第三句完成交付。'


@pytest.mark.parametrize('url', ['https://127.0.0.1:80/v1', 'http://localhost:80/v1', 'http://127.0.0.1:80/v1?q=1', 'http://name@127.0.0.1:80/v1'])
def test_refuses_nonexplicit_owned_endpoint(url):
    with pytest.raises(ValueError):
        require_loopback(url)


def test_rejected_capability_does_not_forward_or_enter_native_ledger(tmp_path):
    archive = tmp_path / 'wire.jsonl'
    with complete_provider(delay=0) as (provider, url):
        with NativeWireRelay(url, archive, actual_native=False) as relay:
            request = Request(relay.url + '/chat/completions', data=b'{}', headers={'Authorization': 'Bearer wrong'})
            with pytest.raises(HTTPError) as error:
                build_opener(ProxyHandler({})).open(request, timeout=10)
            assert error.value.code == 403 and not provider.started.is_set()
    assert not archive.read_text()


def test_rejects_incomplete_sse_instead_of_approving_partial_native_text():
    with pytest.raises(ValueError, match='Incomplete'):
        parse_wire({'http_status': 200, 'outcome': 'completed', 'request': {'stream': True},
            'raw_http_body': 'data: {"id":"partial","choices":[{"delta":{"content":"半句"},"finish_reason":null}]}\n\n'})


def test_upstream_error_body_is_preserved_and_cannot_be_approved_as_native_completion(tmp_path):
    archive = tmp_path / 'wire.jsonl'
    with complete_provider(error_status=503) as (_, url):
        with NativeWireRelay(url, archive, actual_native=False) as relay:
            request = Request(relay.url + '/chat/completions', data=b'{"stream":false}',
                headers={'Authorization': 'Bearer local-eval-only'})
            with pytest.raises(HTTPError) as error:
                build_opener(ProxyHandler({})).open(request, timeout=10)
            body = error.value.read()
            assert error.value.code == 503
    row = json.loads(archive.read_text())
    assert row['http_status'] == 503 and row['raw_http_body'].encode() == body
    assert row['response_body_sha256'] == sha256(body).hexdigest()
    with pytest.raises(ValueError, match='did not complete successfully'):
        parse_wire(row)
