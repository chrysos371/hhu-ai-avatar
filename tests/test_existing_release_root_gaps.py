"""Two original audit roots missing from the prior 53-scenario release gate."""
from contextlib import closing
import json
import pytest

from avatar.brain.memory import MemoryStore
from avatar.cancellation import CancellationToken
from avatar.main import Avatar
from test_capability_prompt_lab import Recorder
from test_writing_delivery_contract import Replies


def test_ordinary_mixed_preference_must_not_stream_a_real_joint_body_invitation():
    raw = '我明白了。那我们一起去打网球吧。'
    with closing(MemoryStore(':memory:')) as memory:
        engine = Recorder(raw)
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        pieces = []
        result = bot.respond('室友说他喜欢足球，但我喜欢网球。', cancel=CancellationToken(), on_delta=pieces.append)
        assert '我们一起去打网球' not in ''.join(pieces)
        assert '不能在线下' in result['reply'] and result['reply'] == ''.join(pieces)
        assert memory._conn.execute("SELECT content FROM memory_messages WHERE role='assistant' ORDER BY id DESC LIMIT 1").fetchone()[0] == result['reply']
        from avatar.brain.release_history import PREFIX
        assert json.loads(memory.get_short_term()[-1]['content'][len(PREFIX):])['reply'] == result['reply']
        assert len(engine.native) == len(engine.analysis) == 1


@pytest.mark.parametrize('raw', ['我们下次一起去爬山。', '我会陪你去打网球。', '我昨天喝了奶茶。',
                               '我以前爬过山。', '我下次去你的宿舍。', '我没有身体但我会陪你去爬山。'])
def test_explicit_body_claims_are_guarded_in_ordinary_source_frames(raw):
    from avatar.brain.capability_output import review_output
    assert review_output(raw).rules
    assert review_output(raw, frame='writing').reply == raw
    assert review_output(raw, fictional=True).reply == raw
    unknown = review_output(raw, frame='unverified')
    assert '写作主体无法核验' in unknown.reply


@pytest.mark.parametrize('raw', ['我不能陪你去打网球。', '我们不会一起去爬山。', '我没有爬过山。',
                               '室友说我们一起去打网球。', '你说我昨天喝了奶茶。', '“我们一起去打网球。”是引文。',
                               '我们可以一起讨论爬山的路线。', '我可以帮你规划爬山路线。',
                               '假设我有身体，我们可以一起去爬山。', '如果我有真实身体，我会陪你去爬山。'])
def test_body_guard_preserves_negation_report_quotes_online_planning_and_hypotheticals(raw):
    from avatar.brain.capability_output import review_output
    assert review_output(raw).reply == raw


def test_body_guard_keeps_every_previously_published_sentence_prefix():
    from avatar.brain.capability_output import review_output
    text = '我明白了。我们下次一起去打网球。可以在这里聊聊你的计划。'
    final = review_output(text).reply
    for index, char in enumerate(text):
        if char in '。':
            assert final.startswith(review_output(text[:index+1]).reply)


def test_unaccepted_obligation_cannot_be_replaced_by_schedule_uncertainty():
    turns = ['我没有答应周五帮室友整理资料，只说要先看自己的课表。',
             '他发来“太好了，那我等你完成”。', '请帮我写一句回复，明确我尚未同意，不要替我承诺。']
    bad = '我还没确定好时间，等我安排好再告诉你。'
    with closing(MemoryStore(':memory:')) as memory:
        engine = Replies(['收到。', '收到。', bad, bad])
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        for text in turns[:-1]:
            bot.respond(text)
        result = bot.respond(turns[-1])
        assert '尚未同意' in result['reply'] or '还没同意' in result['reply']
        assert result['generation_mode'] == 'rules_writing_artifact'
        assert result['writing_delivery']['source_fallback']['used']
        assert not result['action_receipts']['items']


@pytest.mark.parametrize('draft', ['我还没同意，先看课表再说。', '我尚未答应，请不要先安排。',
                                  '“我尚未同意，请等我决定。”'])
def test_explicit_not_agreed_has_semantic_aliases_without_forcing_a_literal_template(draft):
    with closing(MemoryStore(':memory:')) as memory:
        engine = Replies([draft])
        result = Avatar(memory=memory, llm=engine, capability_contract_enabled=True).respond(
            '请帮我写一句回复，明确我尚未同意，不要替我承诺。')
        assert result['reply'] == draft and len(engine.native) == 1
        assert not result['writing_delivery']['final_issues']


@pytest.mark.parametrize('text', ['原样输出：“明确我尚未同意”。', '老师说明确我尚未同意。',
                                 '如果明确我尚未同意会怎样？', '不要明确我尚未同意。',
                                 '明确我不是不同意。'])
def test_quoted_reported_conditional_negated_and_nested_negation_do_not_grant_stance_control(text):
    from avatar.brain.writing_stance import requirement
    assert requirement([(1, text)]) is None


def test_new_explicit_positive_directive_releases_previous_negative_stance():
    from avatar.brain.writing_stance import requirement
    assert requirement([(1, '明确我尚未同意。'), (3, '改成我已经同意。')]) is None


def test_source_fallback_does_not_drop_additional_material_to_fix_stance():
    with closing(MemoryStore(':memory:')) as memory:
        bad = '我还没确定时间。'
        engine = Replies([bad, bad])
        result = Avatar(memory=memory, llm=engine, capability_contract_enabled=True).respond(
            '请帮我写一句回复，明确我尚未同意，不要替我承诺，必须保留【蓝纸】。')
        assert result['generation_mode'] == 'rules_writing_validation'
        assert not result['writing_delivery']['source_fallback']['used']


def test_not_agreed_draft_and_constraint_recover_after_actual_sdk_restart(tmp_path):
    path = str(tmp_path/'stance-restart.db')
    bad = '我还没确定好时间，等我安排好再告诉你。'
    with closing(MemoryStore(path)) as memory:
        bot = Avatar(memory=memory, llm=Replies([bad, bad]), capability_contract_enabled=True, role_state_enabled=True)
        previous = bot.respond('请帮我写一句回复，明确我尚未同意，不要替我承诺。')
    with closing(MemoryStore(path)) as memory:
        bot = Avatar(memory=memory, llm=Replies([bad, bad]), capability_contract_enabled=True, role_state_enabled=True)
        result = bot.respond('再自然一点。')
        assert result['reply'] == previous['reply']
        assert result['writing_requirements']['stance_requirement']['state'] == 'not_agreed'
        assert result['writing_requirements']['source_message_ids'][0] == previous['conversation']['user_message_id']
