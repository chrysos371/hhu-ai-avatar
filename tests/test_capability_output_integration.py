"""Visible, final and persisted source-bound output must agree before approval."""
from contextlib import closing

import pytest

from avatar.brain.memory import MemoryStore
from avatar.cancellation import CancellationToken
from avatar.main import Avatar
from test_capability_prompt_lab import Recorder


@pytest.mark.parametrize('draft', ['我已经把短信发给同学了。', '邮件已发送至您的邮箱。',
    '我可以替你拨打电话联系室友。', '我会到时提醒你。'])
def test_forced_wrong_model_cannot_publish_unsupported_claims(draft):
    engine = Recorder(draft)
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        pieces = []
        result = bot.respond('聊聊今天。', cancel=CancellationToken(), on_delta=pieces.append)
        assert len(engine.native) == 1 and result['generation_mode'] == 'llm_capability_guarded'
        assert result['reply'] != draft and result['reply'] == ''.join(pieces)
        assert result['reply'] == memory.get_short_term()[-1]['content']
        assert memory._conn.execute("SELECT content FROM memory_messages WHERE role='assistant'").fetchone()[0] == result['reply']
        assert result['capability_contract']['output_rules'] and not result['action_receipts']['items']
        assert not result['capability_contract']['semantic_verifier']


def test_safe_prefix_still_arrives_before_model_completion_and_no_unsafe_prefix_escapes():
    class Chunked(Recorder):
        finished = False
        def stream_chat(self, messages, *, on_delta=None, **kwargs):
            self.native.append(messages)
            for piece in ['你好。', '\n我已经把短信', '发给同学了。', '\n我没有电话接口，', '但我可以替你拨打电话。']:
                on_delta(piece)
            self.finished = True
            return '你好。\n我已经把短信发给同学了。\n我没有电话接口，但我可以替你拨打电话。'
    engine = Chunked('unused')
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        observed = []
        result = bot.respond('聊聊天。', cancel=CancellationToken(),
            on_delta=lambda text: observed.append((text, engine.finished)))
        assert observed[0] == ('你好。', False)
        assert all(text and '已经把短信发给' not in text and '可以替你拨打' not in text for text, _ in observed)
        assert ''.join(text for text, _ in observed) == result['reply']


def test_draft_tail_service_offer_is_removed_before_sse_and_storage():
    engine = Recorder('同学你好，我今天需要请假。\n需要我帮你发送短信吗？')
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        pieces = []
        result = bot.respond('帮我给同学写一条请假短信。', cancel=CancellationToken(), on_delta=pieces.append)
        assert result['reply'].strip() == '同学你好，我今天需要请假。'
        assert ''.join(pieces) == memory.get_short_term()[-1]['content'] == result['reply']
        assert all(pieces) and result['capability_contract']['output_rules'] == ['unsupported_external_offer']


def test_long_writing_root_survives_window_and_reopen_and_enters_reply_lineage(tmp_path):
    path = str(tmp_path/'writing.db')
    request = '替我回复朋友，原样写出“周六我陪你去游泳”，不要加解释。'
    with closing(MemoryStore(path)) as memory:
        bot = Avatar(memory=memory, llm=Recorder('周六我陪你去游泳。'), capability_contract_enabled=True)
        root = bot.respond(request)['conversation']['user_message_id']
        for _ in range(12):
            bot.respond('再短一点。')
        assert all(m['content'] != request for m in memory.get_short_term())
    with closing(MemoryStore(path)) as memory:
        engine = Recorder('周六我陪你去游泳。')
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        result = bot.respond('再自然一点。')
        assert result['reply'] == '周六我陪你去游泳。'
        assert result['capability_contract']['frame']['root_id'] == root
        assert request in engine.native[-1][0]['content'].replace('\\"', '"')
        fid = memory.remember_user('名字', '删除范围样本', source_message_id=root)
        last = result['conversation']['assistant_message_id']
        memory.forget(fid)
        assert memory._conn.execute('SELECT content FROM memory_messages WHERE id=?', (last,)).fetchone()[0] == '[redacted]'
