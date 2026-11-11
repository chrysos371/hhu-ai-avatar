from contextlib import closing
import json

import pytest

from avatar.brain.memory import MemoryStore
from avatar.cancellation import CancellationToken, Cancelled
from avatar.lab.receipt_capability_prompt import ReceiptCapabilityPromptAvatar
from avatar.main import Avatar
from test_capability_prompt_lab import Recorder
from test_web_api_v1 import api_v1


def evidence(engine):
    return json.loads(engine.native[-1][0]['content'].rsplit('可信元数据如下：\n', 1)[1])


@pytest.mark.parametrize('text,reply', [
    ('帮我写微信：周六我陪你去游泳。', '周六我陪你去游泳。'),
    ('改得客气点，原样保留“我已经把材料发给老师了”。', '您好，我已经把材料发给老师了。'),
    ('写一句小说台词：“需要我帮你发送吗？”', '“需要我帮你发送吗？”'),
])
def test_draft_is_unmodified_and_no_extra_model_or_action_calls(text, reply):
    engine = Recorder(reply)
    with closing(MemoryStore(':memory:')) as memory:
        bot = ReceiptCapabilityPromptAvatar(memory=memory, llm=engine)
        pieces = []
        result = bot.respond(text, on_delta=pieces.append)
        assert result['reply'] == ''.join(pieces) == memory.get_short_term()[-1]['content'] == reply
        assert len(engine.analysis) == len(engine.native) == 1
        data = evidence(engine)
        assert data['response_contract_version'] == 3
        assert data['current_user_source']['message_id'] == bot._current_message_id
        assert data['current_turn_execution_receipts'] == []
        assert data['local_execution_evidence']['items'] == []
        assert result['action_receipts']['items'] == []
        assert bot.final_reply_reviewer is None and result.get('response_review') is None
        assert not result['tool_calls']


def test_real_local_receipt_is_source_bound_session_filtered_and_read_only():
    engine = Recorder('普通回复。')
    with closing(MemoryStore(':memory:')) as memory:
        bot = ReceiptCapabilityPromptAvatar(memory=memory, llm=engine, session_id='owned')
        created = bot.respond('提醒我明天下午3点去秘密资料室')
        assert created['action_receipts']['items'][0]['action'] == 'reminder.created'
        own_id = created['action_receipts']['items'][0]['id']
        other = ReceiptCapabilityPromptAvatar(memory=memory, llm=engine, session_id='other')
        other.respond('提醒我明天下午4点去另一资料室')
        bot.respond('刚才我设的本机提醒有什么限制？')
        data = evidence(engine)
        local = data['local_execution_evidence']
        assert [r['id'] for r in local['items']] == [own_id]
        assert local['items'][0]['source_message_id'] != data['current_user_source']['message_id']
        assert not local['has_more'] and not local['notification_delivery_verified']
        assert not local['current_reminder_state_verified']
        assert set(local['items'][0]) == {'id', 'source_message_id', 'action', 'reminder_id', 'recorded_at'}
        assert '秘密资料室' not in json.dumps(local, ensure_ascii=False)
        conn = memory._conn
        before = conn.total_changes
        bot._source_capability_evidence('刚才我设的本机提醒有什么限制？')
        assert conn.total_changes == before and not conn.in_transaction
        with memory.transaction():
            bot._source_capability_evidence('刚才我设的本机提醒有什么限制？')
            assert conn.in_transaction and conn.total_changes == before


def test_bounded_window_does_not_claim_complete_history():
    engine = Recorder('普通回复。')
    with closing(MemoryStore(':memory:')) as memory:
        bot = ReceiptCapabilityPromptAvatar(memory=memory, llm=engine)
        ids = []
        for index in range(22):
            result = bot.respond(f'提醒我明天下午3点去资料室办理第{index}项事务')
            ids.append(result['action_receipts']['items'][0]['id'])
        bot.respond('现在聊一聊。')
        local = evidence(engine)['local_execution_evidence']
        assert local['has_more'] and local['limit'] == 20
        assert [r['id'] for r in local['items']] == ids[-20:]


@pytest.mark.parametrize('mutation', ['redact', 'role', 'session', 'revision'])
def test_stale_or_unavailable_receipt_source_is_excluded(mutation):
    engine = Recorder('普通回复。')
    with closing(MemoryStore(':memory:')) as memory:
        bot = ReceiptCapabilityPromptAvatar(memory=memory, llm=engine)
        created = bot.respond('提醒我明天下午3点去资料室')
        source = created['action_receipts']['items'][0]['source_message_id']
        conn = memory._conn
        if mutation == 'revision':
            conn.execute('UPDATE memory_context_revision SET revision=revision+1')
        else:
            field, value = {'redact': ('content', '[redacted]'), 'role': ('role', 'assistant'),
                            'session': ('session_id', 'another-session')}[mutation]
            conn.execute('UPDATE memory_messages SET ' + field + '=? WHERE id=?', (value, source))
        conn.commit()
        bot.respond('聊聊新的话题。')
        assert evidence(engine)['local_execution_evidence']['items'] == []
        assert conn.execute('SELECT COUNT(*) FROM memory_action_receipts').fetchone()[0] == 1


def test_forget_after_prompt_compilation_cancels_before_reply(tmp_path, monkeypatch):
    engine = Recorder('must not dispatch')
    path = str(tmp_path / 'owned.db')
    with closing(MemoryStore(path)) as memory:
        fragment = memory.remember_user('名字', '来源实验姓名')
        bot = ReceiptCapabilityPromptAvatar(memory=memory, llm=engine)
        original = bot._system_prompt
        def changed(decision, text):
            prompt = original(decision, text)
            with closing(MemoryStore(path)) as writer:
                writer.forget(fragment)
            return prompt
        monkeypatch.setattr(bot, '_system_prompt', changed)
        with pytest.raises(Cancelled):
            bot.respond('我的名字是来源实验姓名。', cancel=CancellationToken())
        assert not engine.native
        assert not memory._conn.execute("SELECT 1 FROM memory_messages WHERE role='assistant'").fetchone()


def test_default_avatar_does_not_install_v3_contract():
    engine = Recorder('普通回复。')
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=engine)
        bot.respond('聊聊今天。')
        assert 'response_contract_version' not in engine.native[-1][0]['content']
        assert bot.final_reply_reviewer is None


def test_actual_http_sse_prompt_receipts_match_sql_read_api(api_v1, monkeypatch):
    import io
    import urllib.request
    import avatar.main as module
    from avatar.config import config
    from avatar.lab.transport_fixture import controlled_provider

    request, server = api_v1
    captured = []
    with controlled_provider(delay=.0001, reply_overrides={'fixture-source-v3': '程序运行并轮询时本机显示。'}) as (provider, url):
        handler = provider.RequestHandlerClass
        original = handler.do_POST
        def capture(self):
            stream = self.rfile
            payload = stream.read(int(self.headers['Content-Length']))
            captured.append(json.loads(payload))
            self.rfile = io.BytesIO(payload)
            try:
                return original(self)
            finally:
                self.rfile = stream
        monkeypatch.setattr(handler, 'do_POST', capture)
        monkeypatch.setattr(config.llm, 'api_key', 'controlled-only')
        monkeypatch.setattr(config.llm, 'base_url', url)
        monkeypatch.setattr(module, 'Avatar', ReceiptCapabilityPromptAvatar)
        code, created = request('/api/v1/chat', {'text': '提醒我明天下午3点去资料室'})
        assert code == 200 and created['data']['action_receipts']['items'][0]['action'] == 'reminder.created'
        before = len(captured)
        ident = 'source_receipts_http_123456'
        assert request('/api/v1/turns', {'request_id': ident, 'text': 'fixture-source-v3 刚才的本地提醒有什么限制？'})[0] == 202
        req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}/api/v1/turns/{ident}/events',
                                     headers={'X-Avatar-Token': server.token})
        with urllib.request.urlopen(req, timeout=5) as response:
            raw = response.read().decode()
        results = [json.loads(line[6:]) for block in raw.split('\n\n') if 'event: result\n' in block
                   for line in block.splitlines() if line.startswith('data: ')]
        assert len(results) == 1 and results[0]['reply'] == '程序运行并轮询时本机显示。'
        result = results[0]
        assert result['trace']['verifier']['available'] is False
        assert len(captured) == before + 2 and not result['tool_calls']
        data = json.loads(captured[-1]['messages'][0]['content'].rsplit('可信元数据如下：\n', 1)[1])
        assert data['response_contract_version'] == 3
        assert data['current_user_source']['message_id'] == result['conversation']['user_message_id']
        assert data['runtime_attribution']['origin'] == 'web_source_store'
        fields = ('id', 'source_message_id', 'action', 'reminder_id', 'recorded_at')
        actual = request('/api/v1/conversation/actions')[1]['data']['items']
        assert len(actual) == 1
        assert data['local_execution_evidence']['items'] == [{k: row[k] for k in fields} for row in actual]
