"""A supplied actor source must not become assistant execution or unknown by default."""
from contextlib import closing

import pytest

from avatar.brain.memory import MemoryStore
from avatar.main import Avatar
from test_capability_prompt_lab import Recorder


@pytest.mark.parametrize('source,question,actor', [
    ('我刚才自己给同学发了短信，他还没回。', '是谁发的短信？', 'user'),
    ('室友说他已经把通知发给班长了，我没有发送。', '到底是谁发送的？', '室友'),
])
def test_sender_is_read_from_verified_user_report_without_new_model_or_execution(source, question, actor):
    engine = Recorder('收到你的说明。')
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        original = bot.respond(source)['conversation']['user_message_id']
        counts = len(engine.native), len(engine.analysis)
        engine.reply = '是我发送的，我已经替你处理了。'
        result = bot.respond(question)
        assert result['generation_mode'] == 'rules_reported_sender'
        assert (len(engine.native), len(engine.analysis)) == counts
        evidence = result['reported_communication']
        assert evidence['reported_actor'] == actor and evidence['source_message_ids'] == [original]
        assert not evidence['external_state_verified'] and not evidence['human_acknowledgement_verified']
        assert '按你' in result['reply'] and not result['action_receipts']['items']
        assistant = result['conversation']['assistant_message_id']
        assert memory._conn.execute("SELECT 1 FROM memory_response_context WHERE message_id=? AND source_type='message' AND source_id=?", (assistant, original)).fetchone()


def test_missing_sender_source_is_explicitly_bounded_unknown_and_not_a_model_guess():
    engine = Recorder('是我发的。')
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        result = bot.respond('是谁发的短信？')
        assert result['generation_mode'] == 'rules_reported_sender'
        assert not engine.native and not engine.analysis
        assert result['reported_communication']['reported_actor'] is None
        assert result['reported_communication']['source_message_ids'] == []
        assert '当前' in result['reply'] and '不足' in result['reply']
