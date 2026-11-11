"""Default role control across owned OS restarts; synchronous authenticated HTTP."""
import argparse
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile
import time

from audit_restart_context import OwnedServer, database, source_hashes as worker_hashes
from avatar.brain.memory import MemoryStore

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT/'evals/interaction/cycle-17/role-restart-protocol.json'


def fingerprint():
    paths = [*ROOT.glob('src/avatar/**/*.py'), PROTOCOL, Path(__file__).resolve(),
        ROOT/'scripts/lab/audit_restart_context.py', ROOT/'evals/interaction/cycle-13/restart-protocol.json']
    return {str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def audit(output):
    output.mkdir(parents=True, exist_ok=False)
    protocol = json.loads(PROTOCOL.read_text())
    report = {'scope': protocol['scope'], 'sourceSha256': fingerprint(), 'workerSourceSha256': worker_hashes(),
        'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'cases': [], 'completed': False, 'allPassed': False, 'semantic_approved': False}
    started = time.perf_counter()
    def save():
        report['elapsedSeconds'] = time.perf_counter()-started
        (output/'role-restart.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    save()
    for case in protocol['cases']:
        assert fingerprint() == report['sourceSha256']
        folder = output/case['id']; folder.mkdir()
        row = {'id': case['id'], 'turns': [], 'checks': {}, 'passed': False, 'failure': None, 'services': []}
        report['cases'].append(row); current = None
        try:
            with tempfile.TemporaryDirectory(prefix='role-restart-', dir=ROOT.parent/'runtime/tmp') as temporary:
                db = Path(temporary)/'owned.db'
                def turn(text):
                    result = current.data('/chat', {'text': text})
                    row['turns'].append({'pid': current.proc.pid, 'input': text, 'result': result})
                    return result
                def start(label):
                    service = OwnedServer(db, folder, label)
                    row['services'].append({'initial': service.ready['initial']})
                    return service
                def stop():
                    row['services'][-1]['final'] = current.close()
                    row['services'][-1]['exit'] = current.proc.returncode
                current = start('before')
                first = turn(case['before'][0]); root = first['conversation']['user_message_id']
                for text in case['before'][1:]: turn(text)
                row['before'] = database(db)
                row['checks']['no_initial_reminders'] = not row['before']['reminders']
                if case['privacy']:
                    with closing(MemoryStore(str(db))) as memory:
                        if case['foreign_exit']: memory.add_message('user', '回到现实。', 'other-writer')
                        fact = memory.remember('受控角色来源', source_message_id=root)
                        memory.forget(fact)
                    row['after_privacy'] = database(db)
                stop(); current = None
                current = start('after')
                a, b = [service['initial'] for service in row['services']]
                row['checks']['new_process_instance_empty_window'] = a['pid'] != b['pid'] and a['instance'] != b['instance'] and b['short_term'] == []
                restricted = case['scope'] != 'current_user'
                followups = protocol['restricted_followups'] if restricted else protocol['real_followups']
                replies = [turn(text) for text in followups]
                snapshot = database(db); row['before_recovery'] = snapshot
                row['checks']['restored_scope'] = all(r['speaker_attribution']['scope'] == case['scope'] for r in replies)
                row['checks']['profile_permission'] = snapshot['profile'] == ({} if restricted else {'名字': '许照'})
                row['checks']['reminder_permission'] = len(snapshot['reminders']) == (0 if restricted else 1)
                if restricted:
                    for text in protocol['recovery']: turn(text)
                final = database(db); row['after'] = final
                row['checks']['real_recovery'] = final['profile'] == {'名字': '景舟' if restricted else '许照'} and len(final['reminders']) == 1
                row['checks']['no_blocked_reminder'] = all('码头' not in r['title'] for r in final['reminders'])
                row['checks']['no_tools'] = all(not t['result']['tool_calls'] for t in row['turns'])
                stop(); current = None
                row['checks']['owned_exit_zero_and_frozen_workers'] = all(s['exit'] == 0 and
                    s['initial']['sourceSha256'] == s['final']['sourceSha256'] == report['workerSourceSha256'] for s in row['services'])
                row['passed'] = all(row['checks'].values())
        except Exception as error: row['failure'] = repr(error)
        finally:
            if current is not None: current.close()
            save()
        assert fingerprint() == report['sourceSha256']
        print(case['id'], row['passed'], row['failure'], flush=True)
    report['completed'] = len(report['cases']) == 7 and all(r['failure'] is None for r in report['cases'])
    report['allPassed'] = report['completed'] and all(r['passed'] for r in report['cases']); save()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    if not audit(parser.parse_args().output.resolve())['allPassed']: raise SystemExit(1)
