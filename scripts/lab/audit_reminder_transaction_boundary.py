"""Deterministic scheduling at actual local action method entry.

Real SDK and SQLite; no model, external notification or physical device claim.
"""
import argparse
from contextlib import closing
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import tempfile
import time

from avatar.brain.memory import MemoryStore
from avatar.cancellation import CancellationToken, Cancelled
from avatar.main import Avatar

ROOT = Path(__file__).resolve().parents[2]


def audit(output):
    if output.exists(): raise FileExistsError(output)
    paths = [*ROOT.glob('src/avatar/**/*.py'), Path(__file__).resolve()]
    report = {'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'source_sha256': {str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest() for p in sorted(paths)},
              'scope': 'Real Avatar SDK and SQL writes; deterministic store-entry scheduling hook. No model, network, notification delivery or random concurrency rate.',
              'completed': False, 'cases': []}
    def save(): output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    save()
    class Engine:
        available = False
    for operation in ('create', 'set_status', 'claim_due'):
        for change in ('normal', 'cancel', 'forget'):
            row = {'operation': operation, 'change': change, 'injected': False, 'cleanup': False}
            report['cases'].append(row)
            with tempfile.TemporaryDirectory(prefix='reminder-boundary-', dir=ROOT.parent/'runtime/tmp') as folder:
                path = str(Path(folder)/'owned.db'); token = CancellationToken()
                bot = Avatar(db_path=path, llm=Engine())
                fragment = bot.memory.remember_user('名字', '动作事务实验名')
                if operation != 'create':
                    seeded = bot.reminders.create('提醒我明天下午3点事务正控')
                    if operation == 'claim_due':
                        with bot.memory.transaction():
                            bot.memory._conn.execute('UPDATE memory_reminders SET due_at=? WHERE id=?',
                                                     (time.time()-10, seeded['id']))
                row['before'] = bot.reminders.list()
                original = getattr(bot.reminders, operation)
                def scheduled(*args, **kwargs):
                    assert not bot.memory._conn.in_transaction
                    row['entry_revision'] = bot.memory.context_revision
                    if change == 'cancel': token.cancel()
                    elif change == 'forget':
                        with closing(MemoryStore(path)) as writer: writer.forget(fragment)
                    row['injected'] = True
                    row['after_change_revision'] = bot.memory.context_revision
                    return original(*args, **kwargs)
                setattr(bot.reminders, operation, scheduled)
                text = ('提醒我明天下午3点事务正控' if operation == 'create' else
                        '取消提醒'+str(seeded['id']) if operation == 'set_status' else '你好')
                try:
                    try:
                        result = bot.respond(text, cancel=token)
                        row['terminal'] = 'result'; row['reply'] = result['reply']
                    except Cancelled as error:
                        row['terminal'] = 'cancelled'; row['error'] = str(error)
                    row['after'] = bot.reminders.list()
                    row['business_changed'] = row['before'] != row['after']
                    row['current_revision'] = bot.memory.context_revision
                    row['token_cancelled'] = token.cancelled
                    row['assistant_count'] = bot.memory._conn.execute(
                        "SELECT count(*) FROM memory_messages WHERE role='assistant'").fetchone()[0]
                    assert row['injected']
                finally:
                    bot.memory.close(); save()
            row['cleanup'] = not Path(folder).exists(); save()
    assert all(sha256((ROOT/name).read_bytes()).hexdigest() == expected
               for name, expected in report['source_sha256'].items())
    report['completed'] = True; save()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    result = audit(parser.parse_args().output)
    for row in result['cases']:
        print(row['operation'], row['change'], row['terminal'], 'SQL changed', row['business_changed'],
              'assistant', row['assistant_count'], 'revision', row['current_revision'])
