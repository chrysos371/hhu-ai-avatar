"""One immutable page/phase group of three actual browser/app HTTP observations."""
import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from urllib.request import Request, build_opener, ProxyHandler
from browser_common import ROOT, BASE, PROTOCOL, digest, verify

sys.path.insert(0, str(ROOT / 'src'))
import avatar.main
import avatar.web
import avatar.web_api
import avatar.web_state
import avatar.brain.emotion
from avatar.brain.memory import MemoryStore
from avatar.config import config
from avatar.paths import project_data_root
from avatar.web import create_server

parser = argparse.ArgumentParser()
parser.add_argument('--phase', required=True, choices=('before', 'after'))
parser.add_argument('--page', required=True, choices=('emotion', 'dashboard'))
parser.add_argument('--freeze', required=True, type=Path)
parser.add_argument('--expected-freeze-sha256', required=True)
args = parser.parse_args()
frozen = verify(args.freeze, args.expected_freeze_sha256, args.phase)
protocol = json.loads(PROTOCOL.read_text())
output = BASE / '实验' / (args.phase + '-' + args.page)
output.mkdir(parents=True, exist_ok=False)
target = output / 'evaluation.json'
config.llm.api_key = ''
config.embedding.model = ''
opener = build_opener(ProxyHandler({}))
modules = (avatar.main, avatar.web, avatar.web_api, avatar.web_state, avatar.brain.emotion)
report = {'scope': protocol['scope'], 'phase': args.phase, 'page': args.page, 'provider': 'offline_rules',
    'actual_native_model_or_gpu': False, 'actual_browser_and_app_http': True, 'app_os_restart_claim': False,
    'source_ref': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
    'freeze_path': str(args.freeze.resolve()), 'freeze_sha256': args.expected_freeze_sha256,
    'frozen_inputs': frozen, 'runtime_module_sha256': {str(Path(m.__file__).resolve().relative_to(ROOT)): digest(m.__file__) for m in modules},
    'cases': [], 'completed': False, 'failure': None}


def save():
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


save()
try:
    for repetition in range(1, protocol['repetitions_per_page_phase'] + 1):
        verify(args.freeze, args.expected_freeze_sha256, args.phase)
        owned = Path(tempfile.mkdtemp(prefix='c35-browser-', dir=project_data_root() / 'tmp'))
        server = create_server(str(owned / 'owned.db'), port=0, legacy_writes=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f'http://127.0.0.1:{server.server_port}'
        row = {'repetition': repetition, 'owned_runtime_dir': str(owned), 'completed': False, 'server_closed': False}
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
                fragment = writer.remember('C35浏览器缓存边界来源。', source_message_id=source)
            env = dict(os.environ)
            env['PLAYWRIGHT_BROWSERS_PATH'] = str(project_data_root() / 'runtime/playwright')
            env['FONTCONFIG_FILE'] = str(project_data_root() / 'runtime/browser-libs/fontconfig.xml')
            env['LD_LIBRARY_PATH'] = str(project_data_root() / 'runtime/browser-libs/extracted/usr/lib/x86_64-linux-gnu')
            command = [str(project_data_root() / 'runtime/node-npm/node_modules/node/bin/node'), str(BASE / '审计/browser_probe.cjs')]
            run = subprocess.run(command, input=json.dumps({'base_url': url, 'token': server.token,
                'fragment_id': fragment, 'page': args.page, 'phase': args.phase,
                'observation_ms': protocol['fixed_observation_after_boundary_ms'],
                'eventual_timeout_ms': protocol['eventual_readiness_timeout_ms'],
                'screenshot': str(output / f'repetition-{repetition}-after-1s.png')}),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=ROOT, env=env, timeout=45)
            row.update(browser_exit_code=run.returncode, raw_browser_stdout=run.stdout, raw_browser_stderr=run.stderr)
            save()
            assert run.returncode == 0, run.stderr
            row['browser'] = json.loads(run.stdout)
            with closing(MemoryStore(server.db_path)) as reader:
                row['revision_after'] = reader.context_revision
                row['source_after'] = dict(reader._conn.execute('SELECT * FROM memory_messages WHERE id=?', (source,)).fetchone())
                assert row['revision_after'] == 1 and row['source_after']['content'] == '[redacted]'
            row['completed'] = True
        finally:
            server.shutdown()
            thread.join(10)
            server.server_close()
            row['server_closed'] = not thread.is_alive()
            save()
    verify(args.freeze, args.expected_freeze_sha256, args.phase)
    report['completed'] = True
    save()
except BaseException as error:
    report['failure'] = repr(error)
    save()
    raise
print('Completed', args.phase, args.page, '3actual browser/offline-rule cases; stale1s',
    sum(row['browser']['stale_at_fixed_observation'] for row in report['cases']), '/3;0native/GPU.')
