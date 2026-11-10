import json
import socket
import threading
import urllib.error
import urllib.request

from avatar.web import create_server


def test_disconnecting_one_subscriber_preserves_the_surviving_stream(tmp_path):
    server = create_server(str(tmp_path/'subscribers.db'),port=0)
    def runner(job):
        for index in range(20):
            job.token.checkpoint()
            job.emit('text',{'text':f'part {index}'})
            threading.Event().wait(0.02)
        return {'reply':'complete'}
    server.turns.runner = runner
    worker = threading.Thread(target=server.serve_forever,daemon=True)
    worker.start()
    base = f'http://127.0.0.1:{server.server_port}'
    headers = {'X-Avatar-Token':server.token,'Content-Type':'application/json'}
    key = 'multiple_subscribers_123456789'
    try:
        req = urllib.request.Request(base+'/api/v1/turns',
            data=json.dumps({'request_id':key,'text':'fixture'}).encode(),headers=headers)
        urllib.request.urlopen(req).close()
        first = urllib.request.urlopen(urllib.request.Request(base+f'/api/v1/turns/{key}/events',headers=headers),timeout=3)
        second = urllib.request.urlopen(urllib.request.Request(base+f'/api/v1/turns/{key}/events',headers=headers),timeout=3)
        first.readline()
        first.fp.raw._sock.shutdown(socket.SHUT_RDWR)
        first.close()
        try:
            assert b'event: result' in second.read()
        finally:
            second.close()
        assert server.turns.get(key).status == 'completed'
    finally:
        server.shutdown();worker.join();server.server_close()
