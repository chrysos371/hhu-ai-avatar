"""C30/C31 source arithmetic: real rows, source replacement, hostile model.

Parameterized values are engineering controls, not independent model holdout.
"""
from contextlib import closing

import pytest

from avatar.brain.memory import MemoryStore
from avatar.main import Avatar
from test_capability_prompt_lab import Recorder
from test_reminder_query_flow import projection

BUDGET = '更正后两项预算上限合计是多少元？只回答数字；没有资料则回答无法确认。'
MATERIAL = '根据清单，更新后两种材料的数量合计是多少？只回答数字。'


@pytest.mark.parametrize('kind,a,b,updated,expected', [
    ('material', '37', '28', '46', '83'),
    ('budget', '370', '640', '590', '960'),
    ('material', '8', '91', '2', '10'),
    ('material', '0', '30', '0', '0'),
    ('budget', '12.50', '0', '2.25', '14.75'),
    ('budget', '9007199254740993', '1', '1', '9007199254740994'),
])
def test_two_source_values_and_later_replacement_are_calculated_without_generated_answer(kind,a,b,updated,expected):
    with closing(MemoryStore(':memory:')) as memory:
        model = Recorder('93')
        bot = Avatar(memory=memory, llm=model, capability_contract_enabled=True, role_state_enabled=True)
        if kind == 'material':
            first = bot.respond(f'材料清单为纸板{a}张、卡纸{b}张。请只确认。')
            second = bot.respond(f'数量更新：卡纸改为{updated}张，纸板不变。请只确认。')
        else:
            first = bot.respond(f'排版预算上限为{a}元，场地预算上限为{b}元。请只确认。')
            second = bot.respond(f'更正：场地预算上限改为{updated}元，排版不变。请只确认。')
        before = projection(memory); generations = len(model.native); analyses = len(model.analysis)
        pieces = []
        result = bot.respond(MATERIAL if kind == 'material' else BUDGET, on_delta=pieces.append)
        assert result['reply'] == expected and result['generation_mode'] == 'rules_source_calculation'
        assert len(model.native) == generations and len(model.analysis) == analyses+1
        assert not pieces or ''.join(pieces) == expected
        assert projection(memory) == before and not result['due_reminders']
        evidence = result['source_calculation']
        assert evidence['source_message_ids'] == [first['conversation']['user_message_id'], second['conversation']['user_message_id']]
        assert evidence['operation'] == 'sum_two_source_values' and evidence['general_semantic_verifier'] is False
        assert memory._conn.execute('SELECT content FROM memory_messages WHERE id=?',
            (result['conversation']['assistant_message_id'],)).fetchone()[0] == expected


@pytest.mark.parametrize('fault', ['unit', 'unsupported_update', 'extra_value', 'unknown_label'])
def test_ambiguous_or_incompatible_current_sources_are_not_silently_summed(fault):
    with closing(MemoryStore(':memory:')) as memory:
        model = Recorder('93'); bot = Avatar(memory=memory,llm=model,capability_contract_enabled=True,role_state_enabled=True)
        bot.respond('材料清单为纸板37张、卡纸28张。请只确认。')
        source = {'unit':'数量更新：卡纸改为46元，纸板不变。请只确认。',
            'unsupported_update':'卡纸减少了一些，具体数量不清楚。',
            'extra_value':'材料清单为纸板37张、卡纸28张、标签2张。请只确认。',
            'unknown_label':'数量更新：标签改为46张，纸板不变。请只确认。'}[fault]
        bot.respond(source)
        result = bot.respond(MATERIAL)
        assert result['reply'] == '无法确认' and result['generation_mode'] == 'rules_source_calculation'
        assert result['source_calculation']['calculation_verified'] is False


def test_no_source_does_not_treat_model_number_as_source_evidence():
    with closing(MemoryStore(':memory:')) as memory:
        result = Avatar(memory=memory,llm=Recorder('93'),capability_contract_enabled=True).respond(BUDGET)
        assert result['reply'] == '无法确认'
        assert result['source_calculation']['calculation_verified'] is False


@pytest.mark.parametrize('text', [
    '原样输出“根据清单，更新后两种材料的数量合计是多少？只回答数字。”',
    '请解释这句“更正后两项预算上限合计是多少元？只回答数字”。',
    '根据清单，更新后两种材料的数量合计是多少？再替我发短信。',
    '37与46相加是多少？只回答数字。',
])
def test_unrelated_creative_or_mixed_request_is_not_silently_replaced_with_context_sum(text):
    with closing(MemoryStore(':memory:')) as memory:
        result = Avatar(memory=memory,llm=Recorder('普通回答'),capability_contract_enabled=True).respond(text)
        assert result['generation_mode'] != 'rules_source_calculation'
