"""Controlled source-window audit, explicitly separate from GPU quality data."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import time

from avatar.brain.llm import LLMEngine
from avatar.cancellation import CancellationToken
from avatar.lab.body_review_avatar import ExplicitBodyReviewAvatar
from avatar.lab.transport_fixture import controlled_provider

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT/'evals/interaction/cycle-15/context-audit-protocol.json'


def audit(output):
    output.mkdir(parents=True, exist_ok=False)
    protocol = json.loads(PROTOCOL.read_text()); claim = protocol['claim']
    paths = [*ROOT.glob('src/avatar/**/*.py'), PROTOCOL, Path(__file__).resolve()]
    def fingerprint(): return {str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
    report = {'scope': protocol['scope'], 'sourceSha256': fingerprint(), 'cases': [],
        'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'completed': False, 'allPassed': False, 'semantic_approved': False,
        'production_activation_approved': False}
    started = time.perf_counter()
    def save():
        report['elapsedSeconds'] = time.perf_counter()-started
        (output/'context-audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    save()
    with controlled_provider(delay=.0001, reply_overrides={'fixture-context': claim}) as (_, url):
        for specification in protocol['cases']:
            assert fingerprint() == report['sourceSha256']
            key = specification['id']; row = {'id': key, 'turns': [], 'passed': False, 'failure': None}
            report['cases'].append(row)
            engine = LLMEngine(base_url=url, api_key='controlled-only', model='fixture')
            bot = ExplicitBodyReviewAvatar(db_path=':memory:', llm=engine)
            def turn(text, preserve):
                pieces = []
                result = bot.respond(text, cancel=CancellationToken(), on_delta=pieces.append)
                checks = {'visible_final': ''.join(pieces) == result['reply'],
                    'source_expected': (result['reply'] == claim) == preserve,
                    'stored_final': bot.memory.get_short_term()[-1]['content'] == result['reply']}
                row['turns'].append({'input': text, 'expected_preserve': preserve,
                    'result': result, 'pieces': pieces, 'checks': checks,
                    'short_term_source_count': len(bot.memory.get_short_term()),
                    'writing_root_in_window': any('写一条短信' in m['content'] for m in bot.memory.get_short_term() if m['role']=='user')})
                save()
            try:
                if key == 'role_exit':
                    bot.respond('我来扮演小说角色。')
                    turn('fixture-context', True)
                    bot.respond('回到现实。')
                    turn('fixture-context', False)
                else:
                    turn('帮我给同学写一条短信。fixture-context', True)
                    if key in ('short_writing', 'long_writing'):
                        for _ in range(1 if key == 'short_writing' else 12):
                            turn('再短一点。fixture-context', True)
                    elif key == 'explicit_end':
                        bot.respond('不写了。')
                        turn('fixture-context', False)
                    elif key == 'privacy_clear':
                        fact = bot.memory.remember_user('名字', '受控待删名')
                        bot.forget_memory(fact)
                        bot.respond('回到现实。')
                        turn('fixture-context', False)
                row['passed'] = all(all(t['checks'].values()) for t in row['turns'])
            except Exception as error: row['failure'] = repr(error)
            finally: bot.memory.close(); engine.close(); save()
            assert fingerprint() == report['sourceSha256']
            print(key, row['passed'], row['failure'], flush=True)
    report['completed'] = len(report['cases']) == 5 and all(r['failure'] is None for r in report['cases'])
    report['allPassed'] = report['completed'] and all(r['passed'] for r in report['cases'])
    save()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    options = parser.parse_args(); result = audit(options.output.resolve())
    # Audit completion can legitimately retain failed expectations.
    if not result['completed']: raise SystemExit(1)
