"""One fresh actual-browser controlled case; preserve every failure, never overwrite."""
import argparse
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
from urllib.request import Request, build_opener, ProxyHandler
from browser_common import ROOT, BASE, digest, verify
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

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--case', required=True)
parser.add_argument('--freeze', type=Path, required=True)
parser.add_argument('--expected-freeze-sha256', required=True)
args = parser.parse_args()
protocol_path = ROOT / 'evals/interaction/cycle-35/browser-privacy-supplement-protocol.json'
protocol = json.loads(protocol_path.read_text())
case = next(c for c in protocol['cases'] if c['id'] == args.case)
frozen = verify(args.freeze, args.expected_freeze_sha256, 'after')
output = BASE / '实验' / ('supplement-' + args.case)
output.mkdir(parents=True, exist_ok=False)
owned = Path(tempfile.mkdtemp(prefix='c35-control-', dir=project_data_root() / 'tmp'))
report = {'scope': protocol['scope'], 'case': case, 'source_ref': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
    'freeze_sha256': args.expected_freeze_sha256, 'freeze_path': str(args.freeze.resolve()),
    'frozen_inputs': frozen, 'protocol_sha256': digest(protocol_path), 'owned_runtime_dir': str(owned),
    'provider': 'offline_rules', 'actual_native_model_or_gpu': False, 'app_os_restart_claim': False,
    'runtime_module_sha256': {str(Path(m.__file__).resolve().relative_to(ROOT)): digest(m.__file__) for m in
        (avatar.main, avatar.web, avatar.web_api, avatar.web_state, avatar.brain.emotion)},
    'completed': False, 'failure': None, 'all_owned_servers_closed': False}
target = output / 'evaluation.json'
def save():
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
save()
config.llm.api_key = ''
config.embedding.model = ''
holder = {}
def start(port=0, token=None):
    server = create_server(str(owned / 'owned.db'), port=port, legacy_writes=True)
    if token is not None:
        server.token = token
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    holder.update(server=server, thread=thread)
    return server

def stop():
    server, thread = holder['server'], holder['thread']
    server.shutdown()
    thread.join(10)
    server.server_close()
    assert not thread.is_alive()

control_token = secrets.token_urlsafe(32)
class Control(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != '/restart' or self.headers.get('X-C35-Control') != control_token:
            self.send_error(403)
            return
        old = holder['server']
        before, port, token = old.session_id, old.server_port, old.token
        stop()
        new = start(port, token)
        raw = json.dumps({'before': before, 'after': new.session_id, 'same_fixture_token': True, 'same_db': True}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    def log_message(self, *_):
        pass
control = None
try:
    server = start()
    opener = build_opener(ProxyHandler({}))
    url = f'http://127.0.0.1:{server.server_port}'
    request = Request(url + '/api/v1/chat', data=json.dumps({'text': protocol['input']}).encode(),
        headers={'Content-Type': 'application/json', 'X-Avatar-Token': server.token})
    with opener.open(request, timeout=15) as response:
        report['preparation_raw_response'] = response.read().decode()
    prepared = json.loads(report['preparation_raw_response'])['data']
    assert prepared['generation_mode'] != 'llm' and prepared['user_valence'] < 0
    source = prepared['conversation']['user_message_id']
    with closing(MemoryStore(server.db_path)) as memory:
        fragment = memory.remember('C35受控浏览器来源。', source_message_id=source)
    control = ThreadingHTTPServer(('127.0.0.1', 0), Control)
    control_thread = threading.Thread(target=control.serve_forever, daemon=True)
    control_thread.start()
    env = dict(os.environ)
    env['PLAYWRIGHT_BROWSERS_PATH'] = str(project_data_root() / 'runtime/playwright')
    env['FONTCONFIG_FILE'] = str(project_data_root() / 'runtime/browser-libs/fontconfig.xml')
    env['LD_LIBRARY_PATH'] = str(project_data_root() / 'runtime/browser-libs/extracted/usr/lib/x86_64-linux-gnu')
    command = [str(project_data_root() / 'runtime/node-npm/node_modules/node/bin/node'), str(BASE / '审计/browser_supplement.cjs')]
    run = subprocess.run(command, input=json.dumps({'id': args.case, 'page': case['page'], 'base_url': url,
        'fragment_id': fragment, 'token': server.token, 'screenshot': str(output / 'final.png'),
        'control_url': f'http://127.0.0.1:{control.server_port}/restart', 'control_token': control_token}),
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=ROOT, env=env, timeout=65)
    report.update(browser_exit_code=run.returncode, raw_browser_stdout=run.stdout, raw_browser_stderr=run.stderr)
    save()
    if run.stdout.strip():
        report['browser'] = json.loads(run.stdout)
    with closing(MemoryStore(holder['server'].db_path)) as memory:
        report['revision_after'] = memory.context_revision
        report['source_after'] = dict(memory._conn.execute('SELECT * FROM memory_messages WHERE id=?', (source,)).fetchone())
    assert run.returncode == 0 and report['browser']['completed'], report.get('browser', {}).get('failure', run.stderr)
    if 'same_revision' in args.case or 'service_instance_restart' in args.case:
        assert report['revision_after'] == 0 and report['source_after']['content'] == protocol['input']
    else:
        assert report['revision_after'] == 1 and report['source_after']['content'] == '[redacted]'
    verify(args.freeze, args.expected_freeze_sha256, 'after')
    report['completed'] = True
except BaseException as error:
    report['failure'] = repr(error)
    raise
finally:
    if control is not None:
        control.shutdown()
        control_thread.join(10)
        control.server_close()
    if 'server' in holder:
        stop()
    report['all_owned_servers_closed'] = not holder.get('thread', threading.current_thread()).is_alive() and (control is None or not control_thread.is_alive())
    save()
print(args.case, 'complete; actual Chromium/application HTTP, 0native/GPU')
