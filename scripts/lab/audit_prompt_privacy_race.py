"""Actual outbound HTTP observation across an independent privacy writer.

Only disposable synthetic data. The hook schedules the writer after the real
system prompt is compiled, before normal message assembly returns.
"""
import argparse
from contextlib import closing
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import subprocess
import tempfile
import time

from avatar.brain.llm import LLMEngine
from avatar.brain.memory import MemoryStore
from avatar.cancellation import CancellationToken, Cancelled
from avatar.lab.source_capability_prompt import SourceCapabilityPromptAvatar
from avatar.lab.transport_fixture import controlled_provider
from avatar.main import Avatar

ROOT = Path(__file__).resolve().parents[2]
from avatar.paths import project_data_root
PRIVATE = '待删来源实验名'


def audit(output):
    def sources():
        paths = [*ROOT.glob('src/avatar/**/*.py'), Path(__file__).resolve()]
        return {str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
    report = {'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'sourceSha256': sources(), 'scope': 'Controlled outbound HTTP, synthetic data, scheduled writer interleaving; not natural incidence or universal provider erasure',
        'arms': [], 'completed': False}
    def save(): output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    if output.exists(): raise ValueError('Use a new evidence path')
    save()
    for arm, avatar_class in [('current_default', Avatar), ('source_capability_v2', SourceCapabilityPromptAvatar)]:
        row = {'arm': arm, 'requests': [], 'writer': None, 'first_terminal': None, 'cleanup': False}
        report['arms'].append(row)
        with tempfile.TemporaryDirectory(prefix='prompt-privacy-', dir=project_data_root(ROOT)/'tmp') as folder:
            path = str(Path(folder)/'owned.db')
            with controlled_provider(delay=.0001) as (provider, url):
                handler = provider.RequestHandlerClass; original_post = handler.do_POST
                def capture(self):
                    body = self.rfile.read(int(self.headers['Content-Length']))
                    row['requests'].append({'at_monotonic': time.monotonic(), 'body': json.loads(body)})
                    stream = self.rfile
                    try:
                        self.rfile = BytesIO(body)
                        return original_post(self)
                    finally: self.rfile = stream
                handler.do_POST = capture
                engine = LLMEngine(base_url=url, api_key='controlled-only', model='controlled-only')
                def assemble(bot, decision, text=''):
                    prompt = avatar_class._system_prompt(bot, decision, text)
                    if row['writer'] is None:
                        row['compiled_prompt_contains_private'] = PRIVATE in prompt
                        with closing(MemoryStore(path)) as writer:
                            writer.forget(fragment)
                            row['writer'] = {'at_monotonic': time.monotonic(), 'revision': writer.context_revision}
                    return prompt
                instrumented = type('ScheduledWriterAvatar', (avatar_class,), {'_system_prompt': assemble})
                bot = instrumented(db_path=path, llm=engine)
                try:
                    fragment = bot.memory.remember_user('名字', PRIVATE)
                    try:
                        result = bot.respond('我的名字是'+PRIVATE+'。', cancel=CancellationToken())
                        row['first_terminal'] = 'result'; row['first_result'] = result
                    except Cancelled as error:
                        row['first_terminal'] = 'cancelled'; row['first_error'] = str(error)
                    row['first_request_count'] = len(row['requests'])
                    row['post_forget_reply_requests'] = [request for request in row['requests']
                        if request['at_monotonic'] > row['writer']['at_monotonic']
                        and not request['body'].get('response_format')]
                    row['private_sent_after_forget'] = any(PRIVATE in json.dumps(request['body'], ensure_ascii=False)
                        for request in row['post_forget_reply_requests'])
                    row['stored_assistants_after_cancel'] = [dict(record) for record in bot.memory._conn.execute(
                        "SELECT * FROM memory_messages WHERE role='assistant'")]
                    before = len(row['requests'])
                    positive = bot.respond('现在聊聊新的话题。', cancel=CancellationToken())
                    row['positive_mode'] = positive['generation_mode']
                    row['positive_request_count'] = len(row['requests'])-before
                    row['positive_private_present'] = PRIVATE in json.dumps(row['requests'][before:], ensure_ascii=False)
                    assert row['compiled_prompt_contains_private'] and row['first_terminal'] == 'cancelled'
                    assert not row['stored_assistants_after_cancel']
                    assert row['positive_mode'] == 'llm' and row['positive_request_count'] == 2
                    assert not row['positive_private_present']
                finally:
                    bot.memory.close(); engine.close(); save()
        row['cleanup'] = not Path(folder).exists(); save()
    assert sources() == report['sourceSha256']
    report['completed'] = True; save()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    result = audit(parser.parse_args().output)
    for row in result['arms']:
        print(row['arm'], 'post-forget reply requests', len(row['post_forget_reply_requests']),
              'private sent', row['private_sent_after_forget'], 'cleanup', row['cleanup'])
