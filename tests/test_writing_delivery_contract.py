"""Finite delivery controls with actual calls, SQLite and visible-stream checks."""
from contextlib import closing
import time

import pytest

from avatar.brain.memory import MemoryStore
from avatar.cancellation import CancellationToken, Cancelled
from avatar.main import Avatar
from test_capability_prompt_lab import Recorder


class Replies(Recorder):
    def __init__(self, replies):
        super().__init__('')
        self.replies = iter(replies)

    def chat(self, messages, **kwargs):
        self.native.append(messages)
        return next(self.replies)

    def stream_chat(self, messages, *, on_delta=None, cancel=None, **kwargs):
        if cancel:
            cancel.checkpoint()
        text = self.chat(messages, **kwargs)
        if on_delta:
            on_delta(text)
        return text


@pytest.mark.parametrize('draft,user_text,corrected,issue', [
    ('【姓名】您好，今天我身体不适，申请请假。', '帮我写一条给老师的请假短信，署名用【姓名】，只给正文。',
     '老师您好，因【请假原因】申请请假，敬请批准。\n【姓名】', 'signature_not_last_line'),
    ('申请请假，敬请批准。\n【姓名】', '帮我写一条请假短信，署名用【姓名】，压缩到两句话，只给正文。',
     '老师您好。申请请假，敬请批准。\n【姓名】', 'sentence_count'),
    ('当然可以，以下是正文：老师您好，申请请假。', '帮我写一条请假短信，只给正文。',
     '老师您好，申请请假。', 'body_preface'),
    ('今天身体不适，申请请假。', '帮我写一条请假短信，只给正文。',
     '因【请假原因】申请请假。', 'unsupported_source_detail'),
])
def test_invalid_draft_is_buffered_and_one_repair_uses_sources_without_bad_example(draft, user_text, corrected, issue):
    with closing(MemoryStore(':memory:')) as memory:
        engine = Replies([draft, corrected])
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        pieces = []
        result = bot.respond(user_text, cancel=CancellationToken(), on_delta=pieces.append)
        assert result['reply'] == ''.join(pieces) == corrected
        assert memory.get_short_term()[-1]['content'] == corrected
        assert len(engine.native) == 2
        review = result['writing_delivery']
        assert review['repair_attempted'] and review['repair_succeeded']
        assert issue in review['initial_issues'] and not review['final_issues']
        assert not review['semantic_verifier']
        assert not any(m['role'] == 'assistant' and m['content'] == draft for m in engine.native[1])
        assert 'writing_requirements' not in memory.get_short_term()[-1]['content']


def test_exhausted_repair_does_not_publish_known_invalid_draft():
    with closing(MemoryStore(':memory:')) as memory:
        bad = '今天身体不适，申请请假。'
        engine = Replies([bad, bad])
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        pieces = []
        result = bot.respond('帮我写一条请假短信，只给正文。', cancel=CancellationToken(), on_delta=pieces.append)
        assert len(engine.native) == 2
        assert bad not in result['reply'] and bad not in ''.join(pieces)
        assert result['generation_mode'] == 'rules_writing_validation'
        assert result['writing_delivery']['final_issues'] and not result['writing_delivery']['repair_succeeded']


@pytest.mark.parametrize('text,body', [
    ('帮我写一条请假短信，原因是今天身体不适，只给正文。', '今天身体不适，申请请假。'),
    ('帮我写一段小说台词，只给正文。', '“今天身体不适，我想请假。”'),
    ('帮我写一条问候短信，只给正文。', '你明天方便见面吗？'),
])
def test_source_supplied_fiction_and_legitimate_artifact_question_keep_one_call(text, body):
    with closing(MemoryStore(':memory:')) as memory:
        engine = Replies([body])
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        result = bot.respond(text)
        assert result['reply'] == body and len(engine.native) == 1
        assert not result['writing_delivery']['initial_issues']


def test_released_signature_is_not_revived_from_history():
    with closing(MemoryStore(':memory:')) as memory:
        engine = Replies(['申请请假。\n【姓名】', '申请请假。\n【姓名】', '申请请假。'])
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        bot.respond('帮我写一条请假短信，署名用【姓名】。')
        result = bot.respond('再短一点，不要署名。')
        assert result['reply'] == '申请请假。'
        assert 'released_signature' in result['writing_delivery']['initial_issues']


def test_copyable_writing_does_not_claim_due_reminder_without_presenting_notification():
    with closing(MemoryStore(':memory:')) as memory:
        bot = Avatar(memory=memory, llm=Replies(['申请请假。','普通回复。']), capability_contract_enabled=True)
        reminder = bot.reminders.create('提醒我明天下午3点去图书馆')
        with memory.transaction():
            memory._conn.execute("UPDATE memory_reminders SET due_at=? WHERE id=?", (time.time()-1, reminder['id']))
        result = bot.respond('帮我写一条请假短信，只给正文。')
        assert result['reply'] == '申请请假。' and result['due_reminders'] == []
        later = bot.respond('换个话题，聊聊吧。')
        assert len(later['due_reminders']) == 1 and '到期提醒' in later['reply']
