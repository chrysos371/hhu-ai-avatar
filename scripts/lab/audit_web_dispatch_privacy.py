"""Actual reply-provider HTTP after a controlled tool completion boundary.

The injectable tool session is a fixture, not an external search or MCP wire
test. The default Avatar and WebAgent execute their actual normal paths.
"""
import argparse
from contextlib import asynccontextmanager, closing
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import subprocess
import tempfile
import time
from types import SimpleNamespace

from avatar.brain.llm import LLMEngine
from avatar.brain.memory import MemoryStore
from avatar.cancellation import CancellationToken, Cancelled
from avatar.lab.transport_fixture import controlled_provider
from avatar.main import Avatar
from avatar.tools.web_agent import WebAgent

ROOT = Path(__file__).resolve().parents[2]
from avatar.paths import project_data_root
PRIVATE = '待删联网实验名'


def audit(output):
    if output.exists(): raise ValueError('Use a new evidence path')
    paths = [*ROOT.glob('src/avatar/**/*.py'), Path(__file__).resolve()]
    report = {'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'sourceSha256': {str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest() for p in sorted(paths)},
        'scope': 'Controlled tool session boundary; actual default Avatar/WebAgent and physical reply-provider HTTP; no real internet search/MCP transport or natural incidence estimate',
        'cases': [], 'completed': False}
    def save(): output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    save()
    for change in ('normal', 'cancel_after_tool', 'forget_after_tool'):
        row = {'case': change, 'requests': [], 'fixture_tool_calls': [], 'change': None, 'cleanup': False}
        report['cases'].append(row); token = CancellationToken()
        with tempfile.TemporaryDirectory(prefix='web-dispatch-', dir=project_data_root(ROOT)/'tmp') as folder:
            path = str(Path(folder)/'owned.db')
            class Session:
                async def list_tools(self):
                    return SimpleNamespace(tools=[SimpleNamespace(name=name) for name in ('web_search', 'read_webpage')])
                async def call_tool(self, name, arguments):
                    row['fixture_tool_calls'].append({'name': name, 'arguments': arguments})
                    if change == 'cancel_after_tool': token.cancel()
                    elif change == 'forget_after_tool':
                        with closing(MemoryStore(path)) as writer: writer.forget(fragment)
                    row['change'] = {'at_monotonic': time.monotonic(), 'kind': change}
                    return SimpleNamespace(isError=False, structuredContent={'results': [
                        {'url': 'https://example.com/docs', 'title': '受控合成资料', 'snippet': '这只是本地工具夹具返回。'}]}, content=[])
            @asynccontextmanager
            async def connect(): yield Session()
            with controlled_provider(delay=.0001,
                    reply_overrides={PRIVATE: '受控联网合成回复。'}) as (provider, url):
                handler = provider.RequestHandlerClass; original_post = handler.do_POST
                def capture(self):
                    body = self.rfile.read(int(self.headers['Content-Length']))
                    row['requests'].append({'at_monotonic': time.monotonic(), 'body': json.loads(body)})
                    stream = self.rfile
                    try:
                        self.rfile = BytesIO(body); return original_post(self)
                    finally: self.rfile = stream
                handler.do_POST = capture
                engine = LLMEngine(base_url=url, api_key='controlled-only', model='controlled-only')
                bot = Avatar(db_path=path, llm=engine, web_agent=WebAgent(connect=connect))
                try:
                    fragment = bot.memory.remember_user('名字', PRIVATE)
                    try:
                        result = bot.respond('/search '+PRIVATE, use_web=True, cancel=token)
                        row['terminal'] = 'result'; row['result'] = result
                    except Cancelled as error:
                        row['terminal'] = 'cancelled'; row['error'] = str(error)
                    row['post_change_requests'] = [request for request in row['requests']
                        if request['at_monotonic'] > row['change']['at_monotonic']]
                    row['private_sent_after_change'] = any(PRIVATE in json.dumps(request['body'], ensure_ascii=False)
                                                          for request in row['post_change_requests'])
                    row['stored_assistant_count'] = bot.memory._conn.execute(
                        "SELECT COUNT(*) FROM memory_messages WHERE role='assistant'").fetchone()[0]
                    assert len(row['fixture_tool_calls']) == 1
                    assert row['terminal'] == ('result' if change == 'normal' else 'cancelled')
                    assert row['stored_assistant_count'] == (1 if change == 'normal' else 0)
                finally:
                    bot.memory.close(); engine.close(); save()
        row['cleanup'] = not Path(folder).exists(); save()
    assert all(sha256((ROOT/name).read_bytes()).hexdigest() == digest for name, digest in report['sourceSha256'].items())
    report['completed'] = True; save(); return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    result = audit(parser.parse_args().output)
    for row in result['cases']:
        print(row['case'], 'post-change HTTP', len(row['post_change_requests']),
              'private in request', row['private_sent_after_change'], 'terminal', row['terminal'])
