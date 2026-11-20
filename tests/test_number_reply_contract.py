"""Known C30 format failure: arithmetic correctness and presentation differ."""
from contextlib import closing

import pytest

from avatar.brain.memory import MemoryStore
from avatar.cancellation import CancellationToken
from avatar.main import Avatar
from test_capability_prompt_lab import Recorder

BUDGET = '更正后两项预算上限合计是多少元？只回答数字；没有资料则回答无法确认。'


@pytest.mark.parametrize('question,raw,expected', [
    (BUDGET, '370 + 590 = 960', '960'),
    (BUDGET, '590 + 370 = 960。', '960'),
    (BUDGET, '960。', '960'),
    ('12.50加2.25是多少？请只输出数值。', '12.50 + 2.25 = 14.75', '14.75'),
    (BUDGET, '无法确认。', '无法确认'),
    ('负10加3是多少？只回答数字。', '-10 + 3 = -7', '-7'),
])
def test_source_requested_number_format_keeps_value_and_all_delivery_layers(question, raw, expected):
    with closing(MemoryStore(':memory:')) as memory:
        engine = Recorder(raw)
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        if question == BUDGET and raw != '无法确认。':
            bot.respond('排版预算上限为370元，场地预算上限为640元。请只确认。')
            bot.respond('更正：场地预算上限改为590元，排版不变。请只确认。')
        pieces = []
        result = bot.respond(question, on_delta=pieces.append)
        assert result['reply'] == ''.join(pieces) == expected
        row = memory._conn.execute('SELECT content FROM memory_messages WHERE id=?',
            (result['conversation']['assistant_message_id'],)).fetchone()
        assert row['content'] == expected
        assert result['generation_mode'] == 'llm_format_guarded'
        assert result['format_contract']['applied']
        assert not result['format_contract']['semantic_answer_verified']
        assert len(engine.native) == len(engine.analysis)  # No repair-model call.


@pytest.mark.parametrize('question,raw', [
    (BUDGET, '370 + 590 = 970'),  # Never hide an arithmetic contradiction.
    (BUDGET, '370或590'),
    (BUDGET, '我还需要更多资料。'),
    ('请解释370加590的过程。', '370 + 590 = 960'),
    ('朋友说“只回答数字”，请解释这句话。', '370 + 590 = 960'),
    ('原样写出“370 + 590 = 960”，标题是“只回答数字”。', '370 + 590 = 960'),
])
def test_unknown_wrong_math_and_noninstruction_text_are_not_mined_for_last_number(question, raw):
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=Recorder(raw), capability_contract_enabled=True)
        result = bot.respond(question)
        assert result['reply'] == raw


def test_number_contract_buffers_raw_expression_until_verified_final_value():
    class Parts(Recorder):
        finished = False
        def stream_chat(self, messages, *, on_delta=None, **kwargs):
            self.native.append(messages)
            for part in ['370 + ', '590 = ', '960。']:
                on_delta(part)
            self.finished = True
            return '370 + 590 = 960。'
    with closing(MemoryStore(':memory:')) as memory:
        engine = Parts('unused')
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        observed = []
        result = bot.respond(BUDGET, cancel=CancellationToken(),
            on_delta=lambda text: observed.append((engine.finished, text)))
        assert observed == [(True, '960')]
        assert result['reply'] == '960'


def test_default_keeps_unapproved_formatter_disabled():
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=Recorder('370 + 590 = 960'))
        assert bot.respond(BUDGET)['reply'] == '370 + 590 = 960'
