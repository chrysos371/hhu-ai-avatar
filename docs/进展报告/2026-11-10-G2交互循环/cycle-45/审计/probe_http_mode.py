"""Actual loopback HTTP/SSE, persisted SQL and model-history scope receipt."""
from contextlib import closing
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import urllib.request

import avatar.main
from avatar.brain.memory import MemoryStore
from avatar.brain.reminders import ReminderStore
from avatar.config import config
from avatar.paths import temporary_dir
from avatar.web import create_server
from probe_sdk_mode import CaptureModel, digest, projection
from run_regression import ROOT, snapshot

BASE = Path(__file__).resolve().parents[1]
WORK = BASE/'审计/工作目录/003-真实HTTP与上下文/v2'


def main():
    assert not WORK.exists()
    WORK.mkdir()
    source = snapshot(); model = CaptureModel(); traces = []
    original = avatar.main.Avatar

    class CapturedAvatar(original):
        def __init__(self, *args, **kwargs):
            kwargs['llm'] = model
            super().__init__(*args, **kwargs)

        def respond(self, *args, **kwargs):
            sql = []; self.memory._conn.set_trace_callback(sql.append)
            try:
                result = super().respond(*args, **kwargs)
                traces.append({'input': args[0], 'options': {'mode': kwargs.get('mode', 'chat')},
                    'result': result, 'SQL': sql})
                return result
            finally:
                self.memory._conn.set_trace_callback(None)

    avatar.main.Avatar = CapturedAvatar
    old_embedding = config.embedding.model; config.embedding.model = ''
    try:
        with tempfile.TemporaryDirectory(prefix='c45-http-mode-',dir=temporary_dir()) as directory:
            server = create_server(str(Path(directory)/'actual.db'), port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            base = f'http://127.0.0.1:{server.server_port}'
            calls = []
            def request(path, data=None, *, stream=False):
                req = urllib.request.Request(base+'/api/v1'+path,
                    data=None if data is None else json.dumps(data).encode(),
                    headers={'Content-Type': 'application/json', 'X-Avatar-Token': server.token})
                with urllib.request.urlopen(req,timeout=15) as response:
                    raw = response.read().decode()
                    calls.append({'path': path, 'input': data, 'status': response.status,
                        'response': raw if stream else json.loads(raw)})
                return raw if stream else json.loads(raw)['data']
            try:
                with closing(MemoryStore(server.db_path)) as memory:
                    ReminderStore(memory)  # Explicit fixture schema startup before seeding.
                    now = time.time()
                    with memory.transaction():
                        memory._conn.execute('INSERT INTO memory_reminders(title,due_at,created_at) VALUES (?,?,?)',
                            ('C45HTTP合成私密标题',now+3600,now))
                    before = projection(memory)
                protocol = json.loads((ROOT/'evals/interaction/cycle-45/product-query-protocol.json').read_text())
                for index, case in enumerate(protocol['browser_cases']):
                    text = case['text'].replace('{id}', '1')
                    result = request('/chat', {'text': text, 'mode': 'reminder_query'})
                    assert result['reminder_query']['route'] == case['route']
                    ident = f'c45_actual_query_http_{index:08}'
                    data = {'request_id': ident, 'text': text, 'mode': 'reminder_query'}
                    request('/turns', data)
                    raw = request('/turns/'+ident+'/events', stream=True)
                    results = [json.loads(line[6:]) for block in raw.split('\n\n') if 'event: result\n' in block
                        for line in block.splitlines() if line.startswith('data: ')]
                    assert len(results) == 1 and results[0]['reminder_query']['route'] == case['route']
                    request('/turns', data)  # Duplicate may only return the old job.
                assert not model.analysis and not model.generation and len(traces) == 10
                with closing(MemoryStore(server.db_path)) as memory:
                    after = projection(memory)
                    assert before == after
                    rows = [dict(r) for r in memory._conn.execute('SELECT * FROM memory_messages')]
                    assert len(rows) == 20 and sum(r['role'] == 'user' for r in rows) == 10
                    (WORK/'after-query.sql').write_text('\n'.join(memory._conn.iterdump())+'\n')
                history = request('/conversation')
                assert len([r for r in history['items'] if r.get('result', {}).get('reminder_query')]) == 10
                request('/chat', {'text': '接着聊聊'})
                assert len(model.analysis) == len(model.generation) == 1
                # Default Web reconstructs a conservative allowed suffix. Its
                # existing allowlist excludes query rule results; measure rather
                # than assume it matches the stateful SDK deque policy.
                inherited = 'C45HTTP合成私密标题' in str(model.generation[0])
                assert inherited is False
                assert snapshot() == source
                (WORK/'http-evidence.json').write_text(json.dumps({'verified': True,
                    'head': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                    'collector_sha256': digest(Path(__file__)), 'source_sha256': source,
                    'actual_query_HTTP_turns': 10, 'query_model_calls': 0,
                    'query_business_before': before, 'query_business_after': after,
                    'messages_after_queries': rows, 'calls': calls, 'traces': traces,
                    'query_SQL_dump_sha256': digest(WORK/'after-query.sql'),
                    'subsequent_ordinary_model': {'analysis': model.analysis, 'generation': model.generation,
                        'query_title_in_generation': inherited, 'recover_context': server.recover_context},
                    'scope': 'actual loopback HTTP and SQLite with configured capture model; no native inference'},
                    ensure_ascii=False,indent=2,allow_nan=False)+'\n')
                print('C45 HTTP:10 actual query turns/5 SSE, zero model/writes; Web later context excludes query results')
            finally:
                server.shutdown(); thread.join(); server.server_close()
    finally:
        avatar.main.Avatar = original; config.embedding.model = old_embedding


if __name__ == '__main__':
    main()
