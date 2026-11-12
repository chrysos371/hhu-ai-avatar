"""Three owned actual-browser/offline-rule cache observations, no native model."""
from contextlib import closing
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from urllib.request import Request, build_opener, ProxyHandler

ROOT = Path(__file__).resolve().parents[5]
BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from avatar.brain.memory import MemoryStore
from avatar.config import config
from avatar.web import create_server

protocol = json.loads((ROOT / 'evals/interaction/cycle-34/browser-emotion-cache-supplement.json').read_text())
work = BASE / '审计/工作目录/003-浏览器情绪缓存补审'
work.mkdir(exist_ok=True)
target = work / 'browser-cache-observations.json'
assert not target.exists()
config.llm.api_key = ''
config.embedding.model = ''
opener = build_opener(ProxyHandler({}))
report = {'scope': protocol['scope'], 'actual_native_model_or_gpu': False,
    'actual_browser_and_app_http': True, 'provider': 'offline_rules', 'cases': [], 'completed': False}
def save():
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
save()
for repetition in range(1, protocol['repetitions'] + 1):
    owned = Path(tempfile.mkdtemp(prefix='c34-browser-cache-', dir=ROOT.parent / 'runtime/tmp'))
    server = create_server(str(owned / 'owned.db'), port=0, legacy_writes=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{server.server_port}'
    row = {'repetition': repetition, 'owned_runtime_dir': str(owned), 'completed': False}
    report['cases'].append(row)
    try:
        request = Request(url + '/api/v1/chat', data=json.dumps({'text': protocol['input']}).encode(),
            headers={'Content-Type': 'application/json', 'X-Avatar-Token': server.token})
        with opener.open(request, timeout=15) as response:
            row['preparation_raw_response'] = response.read().decode()
        result = json.loads(row['preparation_raw_response'])['data']
        assert result['generation_mode'] != 'llm' and result['user_valence'] < 0
        source = result['conversation']['user_message_id']
        with closing(MemoryStore(server.db_path)) as writer:
            fragment = writer.remember('浏览器缓存边界来源。', source_message_id=source)
        env = dict(os.environ)
        env['PLAYWRIGHT_BROWSERS_PATH'] = str(ROOT.parent / 'runtime/playwright')
        env['FONTCONFIG_FILE'] = str(ROOT.parent / 'runtime/browser-libs/fontconfig.xml')
        env['LD_LIBRARY_PATH'] = str(ROOT.parent / 'runtime/browser-libs/extracted/usr/lib/x86_64-linux-gnu')
        run = subprocess.run([str(ROOT.parent / 'runtime/node-npm/node_modules/node/bin/node'),
            str(BASE / '审计/probe_browser_emotion_cache.cjs')], input=json.dumps({
                'base_url': url, 'token': server.token, 'fragment_id': fragment,
                'observation_ms': protocol['fixed_observation_after_boundary_ms'],
                'screenshot': str(work / f'repetition-{repetition}-after-1s.png')}),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=ROOT, env=env, timeout=40)
        row.update(browser_exit_code=run.returncode, raw_browser_stdout=run.stdout, raw_browser_stderr=run.stderr)
        save()
        assert run.returncode == 0, run.stderr
        row['browser'] = json.loads(run.stdout)
        with closing(MemoryStore(server.db_path)) as reader:
            row['revision_after'] = reader.context_revision
            row['source_after'] = dict(reader._conn.execute('SELECT * FROM memory_messages WHERE id=?', (source,)).fetchone())
            assert row['revision_after'] == 1 and row['source_after']['content'] == '[redacted]'
        row['completed'] = True
        save()
    finally:
        server.shutdown()
        thread.join(10)
        server.server_close()
report['completed'] = True
save()
print('Completed3 actual browser cache observations; stale at1s:', sum(row['browser']['stale_at_fixed_observation'] for row in report['cases']), '/3; fresh backend cleared and source redacted; no native model/GPU.')
