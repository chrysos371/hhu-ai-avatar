"""Fault-oriented audit probes in disposable state, with raw measurable outcomes."""
from pathlib import Path
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import logging
import socket
import tempfile
import threading
import time
import urllib.error
import urllib.request

import numpy as np

from avatar.brain.llm import LLMEngine
from avatar.brain.memory import MemoryStore
from avatar.config import config
from avatar.face.lipsync import LipSyncEngine
from avatar.lab.transport_fixture import controlled_provider
from avatar.turns import TurnCoordinator
from avatar.web import create_server


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): parser.error('use a new output path')
    config.llm.api_key = ''; config.embedding.model = ''
    result, logs = {}, []
    class Capture(logging.Handler):
        def emit(self, record):
            if len(logs) < 8: logs.append(record.getMessage())
    handler = Capture(); logging.getLogger('avatar.web').addHandler(handler)
    with tempfile.TemporaryDirectory(prefix='g2-audit-') as folder:
        path = str(Path(folder)/'audit.db')
        memory = MemoryStore(path); memory.close()
        server = create_server(path, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        base = f'http://127.0.0.1:{server.server_port}'
        def request(path, data=None):
            req = urllib.request.Request(base+path, data=None if data is None else json.dumps(data).encode(),
                headers={'X-Avatar-Token':server.token,'Content-Type':'application/json'})
            try:
                with urllib.request.urlopen(req,timeout=10) as response: return response.status,response.read()
            except urllib.error.HTTPError as response: return response.code,response.read()
        try:
            paths=['/api/v1/system','/api/v1/speech/capabilities','/api/v1/memory','/api/v1/emotion']
            def read(index):
                code,body=request(paths[index%len(paths)])
                return {'index':index,'path':paths[index%len(paths)],'status':code}
            start=time.perf_counter()
            with ThreadPoolExecutor(max_workers=8) as pool: rows=list(pool.map(read,range(160)))
            result['concurrent_reads']={'workers':8,'requests':160,'seconds':time.perf_counter()-start,
                'non_200':sum(row['status']!=200 for row in rows),'rows':rows,'diagnostics':logs}
            data={'request_id':'audit_privacy_request_123456','text':'我叫审计专用甲'}
            code,body=request('/api/v1/turns',data); assert code==202,(code,body)
            job=json.loads(body)['data']['job_id']; request(f'/api/v1/turns/{job}/events')
            code,body=request('/api/v1/memory')
            fid=next(row['id'] for row in json.loads(body)['data'] if '审计专用甲' in row['content'])
            assert request('/api/forget',{'id':fid})[0]==200
            code,body=request(f'/api/v1/turns/{job}')
            replay_code,replay=request(f'/api/v1/turns/{job}/events')
            result['forgotten_data_cache']={'status_after_forget':code,'cached_result_contains_erased_name':'审计专用甲'.encode() in body,
                'event_replay_status':replay_code,'event_replay_contains_erased_name':'审计专用甲'.encode() in replay}
            coordinator=TurnCoordinator(str(Path(folder)/'ttl.db'),lambda job:{'reply':'done'},ttl=1)
            old=coordinator.submit({'request_id':'audit_expiry_request_123456','text':'expiry'})
            with old.changed: old.changed.wait_for(lambda:old.status=='completed',timeout=3)
            old.created_at-=2
            try: returned=coordinator.get(old.id); expired_served=returned.result is not None
            except Exception: expired_served=False
            result['cache_expiry']={'ttl_seconds':1,'age_seconds':time.time()-old.created_at,'expired_result_still_served':expired_served}
            coordinator.close()
            samples=np.random.default_rng(17).normal(0,0.0003,16000).astype(np.float32)
            frames=LipSyncEngine().analyze(samples,16000)
            result['quiet_noise_lipsync']={'input_rms':float(np.sqrt(np.mean(samples**2))),
                'peak_mouth_open':max(frame.mouth_open for frame in frames),
                'open_fraction':sum(frame.mouth_open>0.05 for frame in frames)/len(frames)}
            started=[]; original=server.process_request_thread
            def tracked(*a): started.append(time.perf_counter()); return original(*a)
            server.process_request_thread=tracked
            sockets=[]
            try:
                for _ in range(40): sockets.append(socket.create_connection(('127.0.0.1',server.server_port)))
                deadline=time.monotonic()+1
                while len(started)<40 and time.monotonic()<deadline: time.sleep(0.01)
                result['connection_bound']={'opened_connections':len(sockets),'request_threads_started':len(started)}
            finally:
                for connection in sockets: connection.close()
        finally:
            server.shutdown();thread.join();server.server_close()
    with controlled_provider(delay=0.02) as (_,url):
        engine=LLMEngine(base_url=url,api_key='audit-local',model='fixture',timeout=0.15)
        start=time.perf_counter();error=None
        try: engine.stream_chat([{'role':'user','content':'fixture-long'}])
        except Exception as exc:error=type(exc).__name__
        finally:engine.close()
        elapsed=time.perf_counter()-start
        result['stream_deadline']={'configured_timeout_seconds':0.15,'elapsed_seconds':elapsed,'exception_type':error,
            'bounded_within_2x':elapsed<=0.3}
    logging.getLogger('avatar.web').removeHandler(handler)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:{a:b for a,b in v.items() if a not in ('rows','diagnostics')} for k,v in result.items()},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
