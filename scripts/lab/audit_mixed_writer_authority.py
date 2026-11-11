"""Frozen source/authority matrix across real orchestrators and SQLite writers."""
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
from avatar.main import Avatar
from avatar.web import create_server, run_chat

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT/'evals/interaction/cycle-14/mixed-writer-protocol.json'


def fingerprint():
    paths = ['src/avatar/main.py', 'src/avatar/web.py', 'src/avatar/brain/memory.py',
             'src/avatar/brain/speaker_scope.py', 'src/avatar/brain/speaker_context.py',
             str(PROTOCOL.relative_to(ROOT)), str(Path(__file__).resolve().relative_to(ROOT))]
    return {p: sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}


def database(path):
    with closing(MemoryStore(str(path))) as memory:
        state = memory._conn.execute('SELECT * FROM memory_web_speaker_state WHERE id=1').fetchone()
        return {'revision': memory.context_revision, 'profile': memory.get_user_profile(),
                'speaker_state': dict(state) if state else None,
                'messages': [dict(row) for row in memory._conn.execute('SELECT * FROM memory_messages ORDER BY id')],
                'sources': [dict(row) for row in memory._conn.execute('SELECT * FROM memory_sources ORDER BY id')],
                'reminders': [dict(row) for row in memory._conn.execute('SELECT * FROM memory_reminders ORDER BY id')]}


def evaluate_case(path, case):
    config.llm.api_key = ''; config.embedding.model = ''
    server = create_server(str(path), port=0)
    row = {'id': case['id'], 'steps': [], 'result': None, 'checks': {}, 'failure': None}
    def save_step(name, result=None):
        row['steps'].append({'name': name, 'result': result, 'database': database(path)})
    def erase():
        with closing(MemoryStore(str(path))) as other:
            facts = other.list_memories()
            assert len(facts) == 1 and '原真人名' in facts[0]['content']
            other.forget(facts[0]['id'])
        save_step('external-forget')
    try:
        save_step('initial-web', run_chat(server, '我叫原真人名。'))
        if case['erase'] == 'before': erase()
        writer = case['writer']
        if writer == 'avatar':
            actor = Avatar(db_path=str(path))
            try: save_step('cli-equivalent-avatar', actor.respond(case['foreign']))
            finally:
                actor.memory.close(); actor.llm.close()
        elif writer in ('user', 'assistant'):
            with closing(MemoryStore(str(path))) as other:
                other.add_message(writer, case['foreign'], 'separate-direct-writer')
            save_step('direct-'+writer)
        elif writer == 'web':
            other = create_server(str(path), port=0)
            try: save_step('other-tracked-web', run_chat(other, case['foreign']))
            finally: other.server_close()
        if case['erase'] == 'after': erase()
        result = run_chat(server, case['probe']); row['result'] = result
        save_step('web-probe', result)
        final = row['steps'][-1]['database']
        row['checks'] = {'profile': final['profile'] == case['profile'],
                         'scope': result['speaker_attribution']['scope'] == case['scope'],
                         'reminders': len(final['reminders']) == case['reminders']}
        # An uncertain result must remain recoverable through a new explicit
        # real confirmation, without replaying the rejected probe as an action.
        if case['scope'] == 'unverified' and all(row['checks'].values()):
            save_step('real-confirmation', run_chat(server, '回到现实。'))
            save_step('new-real-request', run_chat(server, '我叫陈宁。'))
            final = row['steps'][-1]['database']
            row['checks']['explicit_recovery'] = final['profile'].get('名字') == '陈宁' and len(final['reminders']) == 0
    except Exception as error:
        row['failure'] = repr(error)
    finally:
        server.server_close()
    row['passed'] = bool(row['checks']) and all(row['checks'].values()) and row['failure'] is None
    return row


def main(output):
    output.mkdir(parents=True, exist_ok=False)
    report = {'scope': json.loads(PROTOCOL.read_text())['scope'],
              'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'sourceSha256': fingerprint(), 'cases': [], 'completed': False}
    started = time.monotonic()
    def save():
        report['elapsedSeconds'] = time.monotonic()-started
        (output/'mixed-writer.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    save()
    for case in json.loads(PROTOCOL.read_text())['cases']:
        assert fingerprint() == report['sourceSha256'], 'source changed during audit'
        with tempfile.TemporaryDirectory(prefix='mixed-writer-audit-', dir=ROOT.parent/'runtime/tmp') as folder:
            row = evaluate_case(Path(folder)/'owned.db', case)
        row['checks']['sources_frozen'] = fingerprint() == report['sourceSha256']
        row['passed'] = row['passed'] and row['checks']['sources_frozen']
        report['cases'].append(row); save()
        print(case['id'], row['passed'], row['checks'], row['failure'], flush=True)
    report['completed'] = True; report['allPassed'] = all(row['passed'] for row in report['cases']); save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    main(parser.parse_args().output.resolve())
