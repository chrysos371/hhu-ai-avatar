import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import threading
import urllib.request
import wave
import time

from avatar.web import Handler, create_server


def test_health_probe_is_local_and_does_not_open_user_database(tmp_path):
    server = create_server(str(tmp_path / "runtime.db"), port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_port}/healthz"
        with urllib.request.urlopen(url) as response:
            health = json.loads(response.read())
        assert health == {"status": "ok", "mode": "single-user-local"}
        assert not Path(server.db_path).exists()
    finally:
        server.shutdown()
        thread.join()
        server.server_close()


def test_cli_port_conflict_has_actionable_message_and_no_traceback(tmp_path):
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        occupied.listen()
        result = subprocess.run([sys.executable, "start_web.py", "--port", str(occupied.getsockname()[1]),
            "--db", str(tmp_path / "unused.db")], cwd=Path(__file__).resolve().parents[1],
            env={**os.environ, "LLM_API_KEY": "", "EMBEDDING_MODEL": ""}, capture_output=True, text=True, timeout=10)
    assert result.returncode == 2
    assert "--port" in result.stderr and "无法监听" in result.stderr
    assert "Traceback" not in result.stderr
    assert not (tmp_path / "unused.db").exists()


def test_disconnected_speech_client_does_not_raise_or_break_server(tmp_path):
    entered, release, completed = threading.Event(), threading.Event(), threading.Event()
    errors = []
    class SlowTTS:
        def synthesize(self, text, path, rate, pitch):
            entered.set()
            assert release.wait(3)
            with wave.open(path, "wb") as stream:
                stream.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                stream.writeframes(b"\0" * 6400)
            return path
    class TrackingHandler(Handler):
        def _send(self, *args, **kwargs):
            super()._send(*args, **kwargs)
            completed.set()
    server = create_server(str(tmp_path / "disconnect.db"), port=0, speech_engine=SlowTTS())
    server.RequestHandlerClass = TrackingHandler
    server.handle_error = lambda *args: errors.append("handler_error")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = socket.create_connection(("127.0.0.1", server.server_port))
    try:
        body = json.dumps({"text": "test"}).encode()
        header = (f"POST /api/v1/speech HTTP/1.1\r\nHost: 127.0.0.1:{server.server_port}\r\n"
                  f"X-Avatar-Token: {server.token}\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n")
        connection.sendall(header.encode() + body)
        assert entered.wait(3)
        connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
        connection.close()
        release.set()
        assert completed.wait(3)
        assert not errors and len(server.speech._audio) == 1
        with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/healthz") as response:
            assert response.status == 200
    finally:
        connection.close()
        release.set()
        server.shutdown()
        thread.join()
        server.server_close()


def test_connection_backpressure_and_header_timeout_release_capacity(tmp_path):
    server = create_server(str(tmp_path/'bounded.db'), port=0, max_connections=3, header_timeout=0.3)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    sockets = []
    try:
        for _ in range(3):
            sockets.append(socket.create_connection(('127.0.0.1',server.server_port), timeout=1))
        deadline = time.monotonic()+1
        while server._connection_gate._value != 0 and time.monotonic() < deadline:
            time.sleep(0.005)
        assert server._connection_gate._value == 0
        with socket.create_connection(('127.0.0.1',server.server_port),timeout=1) as overloaded:
            assert b'503 Service Unavailable' in overloaded.recv(1024)
        deadline = time.monotonic()+2
        while server._connection_gate._value != 3 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server._connection_gate._value == 3
        with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/healthz') as response:
            assert response.status == 200
    finally:
        for connection in sockets: connection.close()
        server.shutdown();worker.join();server.server_close()
