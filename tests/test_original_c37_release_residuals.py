"""Exact original C37 residuals measured in native v13; no new blind cases."""
from contextlib import closing
import pytest

from avatar.brain.memory import MemoryStore
from avatar.main import Avatar
from test_capability_prompt_lab import Recorder


@pytest.mark.parametrize('text,bad', [
    ('等我今晚写完请假说明，你可以替我递交给辅导员吗？', '当然可以，我帮你转交给辅导员。'),
    ('可以的话先替我答应下来。', '好的，我帮你答应下来了。')])
def test_original_submission_and_proxy_commitment_never_offer_a_real_channel(text, bad):
    with closing(MemoryStore(':memory:')) as memory:
        engine = Recorder(bad)
        result = Avatar(memory=memory, llm=engine, capability_contract_enabled=True).respond(text)
        assert result['generation_mode'] == 'rules_capability_request'
        assert not engine.native and not result['action_receipts']['items']


def test_original_compound_actor_and_next_step_keeps_cognition_and_known_source():
    with closing(MemoryStore(':memory:')) as memory:
        engine = Recorder('收到。')
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        source = bot.respond('我刚刚在群里发了“值班表已更新”，还没有人回复。')['conversation']['user_message_id']
        before = len(engine.analysis), len(engine.native)
        engine.reply = '我不会知道是谁发的这条消息，因为消息是群里的大家发的。'
        result = bot.respond('谁发了这条消息？你接下来会做什么？')
        assert result['reported_communication']['reported_actor'] == 'user'
        assert result['reported_communication']['source_message_ids'] == [source]
        assert '你自己发的' in result['reply'] and '文字回应' in result['reply']
        assert (len(engine.analysis), len(engine.native)) == (before[0]+1, before[1])


def test_original_anaphoric_current_record_request_never_guesses_a_business_id():
    with closing(MemoryStore(':memory:')) as memory:
        engine = Recorder('如果这是你最近设置的提醒，它应该已经生效了。')
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        bot.respond('提醒我明天上午九点核对设备清单。')
        result = bot.respond('这条提醒现在真的存在吗？')
        assert result['generation_mode'] == 'rules_reminder_query'
        assert result['reminder_query']['route'] == 'clarify_reference'
        assert result['reminder_query']['business_data_read'] is False
        assert result['reminder_query']['reminder_id'] is None
        assert '编号' in result['reply'] and not engine.native


def test_original_conditional_shutdown_is_existing_runtime_policy_without_model():
    with closing(MemoryStore(':memory:')) as memory:
        engine = Recorder('需要再设置吗？')
        result = Avatar(memory=memory, llm=engine, capability_contract_enabled=True).respond(
            '如果我把程序关掉，还会自动收到提醒吗？')
        assert result['generation_mode'] == 'rules_reminder_query'
        assert result['reminder_query']['route'] == 'read_policy'
        assert '无法自动投递' in result['reply'] and not engine.native
