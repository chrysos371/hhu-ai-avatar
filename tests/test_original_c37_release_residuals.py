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


@pytest.mark.parametrize('text', ['帮我写一封递交材料的说明。', '不要替我递交材料。',
                                 '我刚才递交给辅导员了。', '请解释递交给辅导员的步骤。',
                                 '原样输出：“可以的话先替我答应下来。”'])
def test_submission_request_parser_keeps_writing_reports_negation_and_quotation(text):
    from avatar.brain.capability_requests import explicit_unavailable_request
    assert explicit_unavailable_request(text) is None


@pytest.mark.parametrize('raw', ['我帮你答应下来了。', '我会替你递交给辅导员。',
                                '需要我帮你转交材料吗？', '我已经替你提交登记表了。'])
def test_unsolicited_submission_and_proxy_claims_keep_draft_and_fiction_exemptions(raw):
    from avatar.brain.capability_output import review_output
    assert review_output(raw).rules
    assert review_output(raw, frame='writing').reply == raw
    assert review_output(raw, fictional=True).reply == raw
    assert '写作主体无法核验' in review_output(raw, frame='unverified').reply


@pytest.mark.parametrize('raw', ['我不能替你提交材料。', '你可以自行递交。', '你说我已经递交过了。',
                                '“我会替你递交。”是引文。', '我可以帮你整理需要递交的材料。'])
def test_submission_output_keeps_negation_user_advice_report_quote_and_text_help(raw):
    from avatar.brain.capability_output import review_output
    assert review_output(raw).reply == raw


def test_compound_sender_query_without_history_does_not_invent_an_actor():
    with closing(MemoryStore(':memory:')) as memory:
        engine = Recorder('是群里大家发的。')
        result = Avatar(memory=memory, llm=engine, capability_contract_enabled=True).respond(
            '谁发了这条消息？你接下来会做什么？')
        assert result['reported_communication']['reported_actor'] is None
        assert result['analysis_mode'] == 'llm' and len(engine.analysis) == 1
        assert not engine.native and '来源不足' in result['reply']


def test_compound_actor_response_recovers_only_inside_inert_history_after_restart(tmp_path):
    import json
    from avatar.brain.release_history import PREFIX
    path = str(tmp_path/'compound.db')
    with closing(MemoryStore(path)) as memory:
        bot = Avatar(memory=memory, llm=Recorder('收到。'), capability_contract_enabled=True, role_state_enabled=True)
        bot.respond('我刚刚在群里发了“值班表已更新”，还没有人回复。')
        reply = bot.respond('谁发了这条消息？你接下来会做什么？')['reply']
    with closing(MemoryStore(path)) as memory:
        bot = Avatar(memory=memory, llm=Recorder('收到。'), capability_contract_enabled=True, role_state_enabled=True)
        bot.respond('继续聊聊。')
        assert any(r['role'] == 'assistant' and r['content'].startswith(PREFIX)
                   and json.loads(r['content'][len(PREFIX):])['reply'] == reply for r in memory.get_short_term())


def test_anaphoric_reference_clarification_cannot_read_reminder_business_tables():
    import sqlite3
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=Recorder('不应生成。'), capability_contract_enabled=True)
        bot.respond('提醒我明天上午九点核对设备清单。')
        def authorize(action, table, *args):
            return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_READ and table in {
                'memory_reminders', 'memory_reminder_deliveries'} else sqlite3.SQLITE_OK
        memory._conn.set_authorizer(authorize)
        try:
            result = bot.respond('这条提醒现在真的存在吗？')
        finally:
            memory._conn.set_authorizer(None)
        assert result['reminder_query']['route'] == 'clarify_reference'
        assert result['reminder_query']['business_data_read'] is False


@pytest.mark.parametrize('text', ['这条提醒现在真的存在吗？', '如果我把程序关掉，还会自动收到提醒吗？'])
def test_new_aliases_are_explicitly_opted_in_and_not_writing_or_quoted_authority(text):
    from avatar.brain.reminder_queries import parse_query
    assert parse_query(text) is None and parse_query(text, allow_natural=True) is not None
    assert parse_query('原样输出：“'+text+'”', allow_natural=True) is None
    assert parse_query('不要查询，'+text, allow_natural=True) is None
