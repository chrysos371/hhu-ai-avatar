from concurrent.futures import ThreadPoolExecutor
import threading
import urllib.request

from avatar.brain.memory import MemoryStore
from avatar.web import create_server


def test_concurrent_read_initialization_and_writes_do_not_upgrade_deadlock(tmp_path):
    path = str(tmp_path / 'concurrent.db')
    MemoryStore(path).close()
    server = create_server(path, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    endpoints = ['/system', '/memory', '/emotion', '/speech/capabilities']
    def read(index):
        request = urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/v1' + endpoints[index % 4],
            headers={'X-Avatar-Token': server.token})
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            assert list(pool.map(read, range(64))) == [200] * 64
        def write(index):
            memory = MemoryStore(path)
            try:
                with memory.transaction():
                    memory.remember(f'独立事实 {index}')
            finally:
                memory.close()
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(write, range(32)))
        memory = MemoryStore(path)
        try:
            assert len(memory.list_memories()) == 32
        finally:
            memory.close()
    finally:
        server.shutdown()
        thread.join()
        server.server_close()
