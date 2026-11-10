"""Regression: an accepted idle socket or slow chat must not freeze static assets."""
import json
import socket
import threading
import urllib.request
from avatar.web import create_server


def test_idle_connection_does_not_block_page(tmp_path):
    dist=tmp_path/'dist';dist.mkdir();(dist/'index.html').write_text('<html>ready</html>')
    server=create_server(str(tmp_path/'memory.db'),port=0,frontend_dir=dist)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    idle=socket.create_connection(server.server_address,timeout=2)
    try:
        # A partial header deterministically occupies an accepted handler.
        idle.sendall(b'GET / HTTP/1.1\r\nHost: ')
        with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/',timeout=2) as response:
            assert response.status==200 and b'ready' in response.read()
    finally:
        idle.close();server.shutdown();thread.join();server.server_close()


def test_slow_chat_does_not_block_page_and_chat_stays_serial(tmp_path,monkeypatch):
    from avatar.main import Avatar
    started=threading.Event();release=threading.Event()
    def slow(self,*args,**kwargs):
        started.set()
        assert release.wait(5)
        return {'reply':'done'}
    monkeypatch.setattr(Avatar,'respond',slow)
    dist=tmp_path/'dist';dist.mkdir();(dist/'index.html').write_text('<html>ready</html>')
    server=create_server(str(tmp_path/'memory.db'),port=0,frontend_dir=dist)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    errors=[]
    def chat():
        request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/chat',
            data=json.dumps({'text':'你好'}).encode(),headers={'X-Avatar-Token':server.token,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(request,timeout=5) as response:response.read()
        except Exception as exc:errors.append(type(exc).__name__)
    worker=threading.Thread(target=chat);worker.start()
    try:
        assert started.wait(3)
        assert not server.chat_lock.acquire(blocking=False)
        with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/',timeout=2) as response:
            assert response.status==200
    finally:
        release.set();worker.join();server.shutdown();thread.join();server.server_close()
    assert not errors


def test_parallel_management_reads_do_not_race_database_migrations(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    server=create_server(str(tmp_path/'memory.db'),port=0)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    def read(index):
        route=['system','persona','qq/contexts'][index%3]
        request=urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/v1/'+route,
                                       headers={'X-Avatar-Token':server.token})
        with urllib.request.urlopen(request,timeout=5) as response:
            assert json.load(response)['error'] is None
            return response.status
    try:
        with ThreadPoolExecutor(max_workers=6) as pool:
            assert list(pool.map(read,range(18)))==[200]*18
    finally:
        server.shutdown();thread.join();server.server_close()
