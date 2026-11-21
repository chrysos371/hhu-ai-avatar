"""Fixed sixty-event installed-package run; controlled HTTP is not model quality."""
from hashlib import sha256
import io
import json
import math
import os
from pathlib import Path
import re
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, build_opener
import zipfile

import avatar
from avatar.lab.transport_fixture import controlled_provider

ASSETS = Path('/data/Users/zrh/data/hhu-ai-avatar')
ROOT = Path('/data/Users/zrh/repo/hhu-ai-avatar')
HERE = Path(__file__).resolve().parent
OUT = ASSETS/'artifacts/release/installed-soak-v2'
BUILD = ASSETS/'artifacts/release/final-build-v4'
REPLY = '第一句已经生成。第二句继续说明。第三句完成交付。'


def digest(p):
    return sha256(p.read_bytes()).hexdigest()


def write(p, value):
    with p.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def resources(pid):
    status = dict(line.split(':', 1) for line in Path(f'/proc/{pid}/status').read_text().splitlines() if ':' in line)
    return dict(rss_kib=int(status['VmRSS'].split()[0]), fd=len(list(Path(f'/proc/{pid}/fd').iterdir())),
                threads=int(status['Threads']))


def sql_snapshot():
    with sqlite3.connect(OUT/'soak.db') as conn:
        counts = {name: conn.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in
                  ('runtime_turn_ledger', 'memory_messages', 'memory_chat_results',
                   'memory_action_receipts', 'memory_reminders', 'memory_role_state')}
        return dict(counts=counts, integrity=conn.execute('PRAGMA integrity_check').fetchone()[0],
                    ledger_status=conn.execute('SELECT status,COUNT(*) FROM runtime_turn_ledger GROUP BY status').fetchall())


def request(base, token, path, data=None):
    req = Request(base+path, data=None if data is None else json.dumps(data, ensure_ascii=False).encode(),
                  headers={'X-Avatar-Token': token, 'Content-Type': 'application/json'})
    try:
        with build_opener(ProxyHandler({})).open(req, timeout=15) as response:
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()


def main():
    assert os.path.ismount('/data') and not OUT.exists()
    assert Path(sys.prefix) == ASSETS/'envs/hhu-ai-avatar-release-final-v3'
    assert 'site-packages' in avatar.__file__ and not Path(avatar.__file__).is_relative_to(ROOT)
    OUT.mkdir()
    installed = Path(avatar.__file__).parent.parent
    with zipfile.ZipFile(next((BUILD/'dist').glob('*.whl'))) as wheel:
        hashes = {name: sha256(wheel.read(name)).hexdigest() for name in wheel.namelist()
                  if name.startswith('avatar/') and not name.endswith('/')}
    assert all(digest(installed/name) == value for name, value in hashes.items())
    started = time.monotonic()
    result = dict(passed=False, installed_avatar=str(avatar.__file__), driver_sha256=digest(Path(__file__)),
                  protocol_sha256=digest(HERE/'短程稳定性协议-v2.md'), build_result_sha256=digest(BUILD/'build-result.json'),
                  installed_sha256=hashes, whole_stage_wallclock_cutoff=None,
                  scope='60 fixed controlled HTTP/SSE events across three actual installed CLI processes; no native, human, physical or multi-day approval',
                  events=[], processes=[], model_requests=0)
    lock = threading.Lock()
    try:
        with controlled_provider(delay=.001) as (provider, url):
            original_post = provider.RequestHandlerClass.do_POST

            def recorded_post(handler):
                body = handler.rfile.read(int(handler.headers['Content-Length']))
                with lock:
                    result['model_requests'] += 1
                    number = result['model_requests']
                    write(OUT/f'model-request-{number:03}.json', dict(path=handler.path,
                          actual_body_sha256=sha256(body).hexdigest(), body=json.loads(body)))
                previous = handler.rfile
                handler.rfile = io.BytesIO(body)
                try:
                    original_post(handler)
                finally:
                    handler.rfile = previous

            provider.RequestHandlerClass.do_POST = recorded_post
            env = dict(os.environ, LLM_API_KEY='local-controlled-soak', LLM_BASE_URL=url, LLM_MODEL='fixture',
                       OPENBLAS_NUM_THREADS='4', OMP_NUM_THREADS='4', EMBEDDING_MODEL='', HHU_AVATAR_DATA_ROOT=str(OUT/'runtime'))
            env.pop('PYTHONPATH', None)
            env.pop('PYTHONHOME', None)
            previous_payload = None
            for epoch in range(3):
                command = [str(Path(sys.executable).parent/'hhu-avatar'), 'web', '--port', '0', '--db', str(OUT/'soak.db')]
                log_path = OUT/f'process-{epoch}.log'
                proc = dict(epoch=epoch, argv=command, resources=[])
                result['processes'].append(proc)
                child = None
                expected_exit = -9 if epoch == 1 else 0
                try:
                    with log_path.open('x') as log:
                        child = subprocess.Popen(command, cwd=OUT, env=env, stdin=subprocess.DEVNULL,
                                                 stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                        proc['pid'] = child.pid
                        proc['start_ticks'] = int(Path(f'/proc/{child.pid}/stat').read_text().rsplit(')', 1)[1].split()[19])
                        ready = time.monotonic()
                        while True:
                            assert child.poll() is None, 'server failed before readiness'
                            match = re.search(r'(http://127\.0\.0\.1:\d+)/#([A-Za-z0-9_-]+)', log_path.read_text())
                            if match:
                                break
                            assert time.monotonic()-ready < 30, 'readiness engineering boundary'
                            time.sleep(.05)
                        base, token = match.groups()
                        if previous_payload:
                            before = result['model_requests']
                            code, body = request(base, token, '/api/v1/turns', previous_payload)
                            write(OUT/f'replay-after-restart-{epoch}.json', dict(status=code, body=json.loads(body)))
                            assert code == 410 and result['model_requests'] == before
                        for index in range(epoch*20, (epoch+1)*20):
                            event_started = time.monotonic()
                            payload = dict(request_id=f'installed_soak_{index:03}_fixed_1234567890',
                                           text=f'短程稳定性检查第{index+1}轮，请简短回应。')
                            before = result['model_requests']
                            code, body = request(base, token, '/api/v1/turns', payload)
                            assert code == 202
                            job = json.loads(body)['data']['job_id']
                            status, stream = request(base, token, f'/api/v1/turns/{job}/events')
                            (OUT/f'event-{index:03}.sse').write_bytes(stream)
                            records = [json.loads(line[6:]) for line in stream.decode().splitlines() if line.startswith('data: ')]
                            assert status == 200 and b'event: result\n' in stream and records[-1]['reply'] == REPLY
                            assert result['model_requests']-before == 2, 'one cognition and one generation required'
                            code, duplicate = request(base, token, '/api/v1/turns', payload)
                            assert code == 202 and result['model_requests']-before == 2
                            assert json.loads(duplicate)['data']['job_id'] == job
                            snapshot = sql_snapshot()
                            counts = snapshot['counts']
                            assert snapshot['integrity'] == 'ok'
                            assert counts['runtime_turn_ledger'] == counts['memory_chat_results'] == index+1
                            assert counts['memory_messages'] == 2*(index+1)
                            assert counts['memory_action_receipts'] == counts['memory_reminders'] == 0
                            assert counts['memory_role_state'] == 1
                            resource = resources(child.pid)
                            proc['resources'].append(resource)
                            event = dict(index=index, epoch=epoch, seconds=time.monotonic()-event_started,
                                         job_id=job, duplicate_status=code, model_requests=2,
                                         resources=resource, sql=snapshot, final=records[-1])
                            write(OUT/f'event-{index:03}.json', event)
                            result['events'].append(event)
                            previous_payload = payload
                        steady = proc['resources'][-10:]
                        proc['rss_range_kib'] = max(x['rss_kib'] for x in steady)-min(x['rss_kib'] for x in steady)
                        proc['fd_range'] = max(x['fd'] for x in steady)-min(x['fd'] for x in steady)
                        assert proc['rss_range_kib'] <= 65536 and proc['fd_range'] <= 4
                        assert all(x['rss_kib'] < 1048576 and x['fd'] < 128 and x['threads'] <= 32 for x in proc['resources'])
                finally:
                    if child is not None:
                        if child.poll() is None:
                            child.send_signal(signal.SIGKILL if epoch == 1 else signal.SIGINT)
                        try:
                            proc['actual_wait_code'] = child.wait(timeout=30)
                        except subprocess.TimeoutExpired:
                            child.kill()
                            proc['actual_wait_code'] = child.wait()
                        proc['pid_retired'] = not Path(f'/proc/{child.pid}').exists()
                        write(OUT/f'process-{epoch}-terminal.json', proc)
                        assert proc['actual_wait_code'] == expected_exit and proc['pid_retired']
            times = sorted(event['seconds'] for event in result['events'])
            result['p95_seconds'] = times[math.ceil(.95*len(times))-1]
            assert len(result['events']) == 60 and result['model_requests'] == 120 and result['p95_seconds'] <= 10
            result['final_sql'] = sql_snapshot()
            assert result['final_sql']['ledger_status'] == [('completed', 60)]
            assert all(digest(installed/name) == value for name, value in hashes.items())
            result['installed_unchanged'] = True
            result['passed'] = True
    except BaseException as error:
        result['error'] = repr(error)
        raise
    finally:
        result['actual_seconds_including_startup_cleanup'] = time.monotonic()-started
        write(OUT/'result.json', result)
    print(json.dumps({k: result[k] for k in ('passed', 'model_requests', 'p95_seconds', 'actual_seconds_including_startup_cleanup')}))


if __name__ == '__main__':
    main()
