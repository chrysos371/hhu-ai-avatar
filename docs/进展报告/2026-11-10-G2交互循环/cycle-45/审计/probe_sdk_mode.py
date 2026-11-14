"""Collect actual SDK source/SQL/model-boundary evidence, no external services."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import subprocess
import time

from avatar.brain.memory import MemoryStore
from avatar.main import Avatar

BASE = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[5]
OUTPUT = BASE / '审计/工作目录/001-真实入口调查/sdk-mode-evidence.json'
SOURCE = ['src/avatar/main.py', 'src/avatar/brain/reminder_queries.py',
    'src/avatar/brain/reminder_query_mode.py', 'src/avatar/brain/reminder_query_targets.py',
    'src/avatar/brain/speaker_context.py', 'src/avatar/brain/speaker_scope.py']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class CaptureModel:
    available = True

    def __init__(self):
        self.analysis, self.generation = [], []

    def chat_analysis(self, messages, **options):
        self.analysis.append({'messages': messages, 'options': options})
        return '{"emotion":{"valence":0,"arousal":0},"facts":[]}'

    def chat(self, messages, **options):
        self.generation.append({'messages': messages, 'options': options})
        return '后续普通聊天的受控回复。'


def projection(memory):
    return {name: [dict(r) for r in memory._conn.execute('SELECT * FROM '+name)]
        for name in ['memory_reminders', 'memory_reminder_deliveries', 'memory_action_receipts']}


def main():
    assert not OUTPUT.exists()
    before_source = {n: digest(ROOT/n) for n in SOURCE}
    cases = []
    for text, expected in [
        ('提醒编号1现在是什么状态？', 'read_state'),
        ('提醒编号1能通过短信送给我吗？', 'read_policy'),
        ('这条提醒取消了吗？', 'clarify_reference'),
        ('提醒编号1的状态和程序运行条件是什么？', 'clarify_intent'),
        ('请取消提醒编号1', 'no_read'),
        ('提醒我明天九点喝水', 'no_read'),
        ('请帮我发短信提醒', 'no_read'),
    ]:
        with closing(MemoryStore(':memory:')) as memory:
            model = CaptureModel()
            bot = Avatar(memory=memory, llm=model, session_id='c45-sdk-actual')
            now = time.time()
            with memory.transaction():
                memory._conn.execute('INSERT INTO memory_reminders(title,due_at,created_at) VALUES (?,?,?)',
                    ('C45合成私密标题：不是用户事实', now-60, now-3600))
            before = projection(memory)
            sql = []; memory._conn.set_trace_callback(sql.append)
            result = bot.respond(text, mode='reminder_query')
            memory._conn.set_trace_callback(None)
            after = projection(memory)
            rows = [dict(r) for r in memory._conn.execute('SELECT * FROM memory_messages')]
            assert result['reminder_query']['route'] == expected
            assert not model.analysis and not model.generation and before == after
            assert [r['role'] for r in rows] == ['user', 'assistant']
            assert result['conversation']['user_message_id'] == result['reminder_query']['source_message_id']
            assert not memory.get_user_profile()
            cases.append({'input': text, 'result': result, 'business_before': before, 'business_after': after,
                'messages': rows, 'SQL': sql, 'model_analysis': [], 'model_generation': []})
            if expected == 'read_state':
                bot.respond('接着聊聊')
                assert len(model.analysis) == len(model.generation) == 1
                assert result['reply'] in str(model.generation[0])
                history = {'analysis': model.analysis, 'generation': model.generation,
                    'query_reply_in_later_generation': True,
                    'scope': 'query turn zero model; subsequent ordinary chat inherits saved history'}
    assert before_source == {n: digest(ROOT/n) for n in SOURCE}
    output = {'verified': True, 'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'],cwd=ROOT,text=True).strip(),
        'collector_sha256': digest(Path(__file__)), 'source_sha256': before_source,
        'actual_query_SDK_turns': len(cases), 'query_model_calls': 0, 'external_or_native_calls': 0,
        'data': 'synthetic seeded rows in actual SQLite; configured capture model, not native model quality',
        'cases': cases, 'later_ordinary_context': history}
    OUTPUT.write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    print('C45 SDK:7 actual query turns, one user each, no model/business writes; later chat history includes query reply')


if __name__ == '__main__':
    main()
