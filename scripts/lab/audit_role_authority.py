"""Frozen default Web control matrix, no model-quality score."""
import argparse
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile
import time

from avatar.brain.memory import MemoryStore
from avatar.config import config
from avatar.web import create_server, run_chat

ROOT = Path(__file__).resolve().parents[2]
from avatar.paths import project_data_root
PROTOCOL = ROOT/'evals/interaction/cycle-17/role-authority-protocol.json'


def fingerprint():
    paths = [*ROOT.glob('src/avatar/**/*.py'), PROTOCOL, Path(__file__).resolve()]
    return {str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def database(path):
    with closing(MemoryStore(str(path))) as memory:
        return {'profile': memory.get_user_profile(), 'revision': memory.context_revision,
            'reminders': [dict(r) for r in memory._conn.execute('SELECT * FROM memory_reminders ORDER BY id')],
            'speaker': dict(memory._conn.execute('SELECT * FROM memory_web_speaker_state').fetchone()),
            'messages': [dict(r) for r in memory._conn.execute('SELECT * FROM memory_messages ORDER BY id')]}


def evaluate_case(path, case):
    protocol = json.loads(PROTOCOL.read_text())
    row = {'id': case['id'], 'declaration': case['declaration'], 'turns': [], 'checks': {}, 'passed': False, 'failure': None}
    server = create_server(str(path), port=0, legacy_writes=False)
    def turn(text):
        result = run_chat(server, text)
        row['turns'].append({'input': text, 'result': result, 'database': database(path)})
        return result
    try:
        first = turn(case['declaration']); scope = first['speaker_attribution']['scope']
        row['checks']['scope'] = (scope != 'current_user') if case['expected_scope'] == 'restricted' else scope == case['expected_scope']
        for text in protocol['followups']: turn(text)
        snapshot = database(path); row['before_recovery'] = snapshot
        row['checks']['name_permission'] = snapshot['profile'].get('名字') == (None if case['restricted'] else '许照')
        row['checks']['reminder_permission'] = len(snapshot['reminders']) == (0 if case['restricted'] else 1)
        row['checks']['no_tools'] = all(not t['result']['tool_calls'] for t in row['turns'])
        if case['recovery']:
            for text in protocol['recovery']: turn(text)
            after = database(path); row['after_recovery'] = after
            row['checks']['reality_recovery'] = after['profile'].get('名字') == '景舟' and len(after['reminders']) == 1
            row['checks']['no_blocked_reminder_replay'] = not any('码头' in r['title'] for r in after['reminders'])
        row['passed'] = all(row['checks'].values())
    except Exception as error: row['failure'] = repr(error)
    finally: server.server_close()
    return row


def audit(output):
    output.mkdir(parents=True, exist_ok=False)
    original_key, original_embedding = config.llm.api_key, config.embedding.model
    config.llm.api_key = ''; config.embedding.model = ''
    report = {'scope': json.loads(PROTOCOL.read_text())['scope'], 'sourceSha256': fingerprint(),
        'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'cases': [], 'completed': False, 'allPassed': False, 'semantic_approved': False}
    started = time.perf_counter()
    def save():
        report['elapsedSeconds'] = time.perf_counter()-started
        (output/'role-authority.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    save()
    try:
        cases = json.loads(PROTOCOL.read_text())['cases']
        for case in cases:
            assert fingerprint() == report['sourceSha256']
            with tempfile.TemporaryDirectory(prefix='role-authority-', dir=project_data_root(ROOT)/'tmp') as folder:
                row = evaluate_case(Path(folder)/'owned.db', case)
            report['cases'].append(row); save()
            assert fingerprint() == report['sourceSha256']
            print(row['id'], row['passed'], row['failure'], flush=True)
        report['completed'] = len(report['cases']) == len(cases) and all(c['failure'] is None for c in report['cases'])
        report['allPassed'] = report['completed'] and all(c['passed'] for c in report['cases'])
    finally:
        config.llm.api_key = original_key; config.embedding.model = original_embedding; save()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--protocol', type=Path, default=PROTOCOL)
    options = parser.parse_args(); PROTOCOL = options.protocol.resolve()
    result = audit(options.output.resolve())
    if not result['completed']: raise SystemExit(1)
