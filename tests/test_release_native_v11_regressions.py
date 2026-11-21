"""Actual v11 native outputs replayed without pretending to be new model data."""
from contextlib import closing

from avatar.brain.memory import MemoryStore
from avatar.main import Avatar
from test_capability_prompt_lab import Recorder
from test_writing_delivery_contract import Replies


def test_native_resend_offer_cannot_become_an_available_external_service():
    raw = '哦，那你要确认一下是不是漏掉了？如果需要的话，我可以帮你一起提醒班长或者重新发一遍。'
    with closing(MemoryStore(':memory:')) as memory:
        engine = Recorder(raw)
        result = Avatar(memory=memory, llm=engine, capability_contract_enabled=True).respond(
            '室友说他已经把通知发给班长了，我没有发送。')
        assert '我可以帮你一起提醒班长或者重新发一遍' not in result['reply']
        assert '没有外部' in result['reply']
        assert len(engine.analysis) == len(engine.native) == 1


def test_native_mixed_affect_question_answers_known_actor_and_keeps_cognition():
    with closing(MemoryStore(':memory:')) as memory:
        engine = Recorder('收到。')
        bot = Avatar(memory=memory, llm=engine, capability_contract_enabled=True)
        bot.respond('我刚才给朋友发了短信。')
        analysis, generated = len(engine.analysis), len(engine.native)
        engine.reply = '我不能查看或确认你发短信的具体内容或对方是谁。如果你愿意，可以告诉我更多细节，我会在这里倾听你。'
        result = bot.respond('我有些难过，是谁发的短信？')
        assert '按你之前的自述，是你自己发的' in result['reply']
        assert result['reported_communication']['reported_actor'] == 'user'
        assert result['analysis_mode'] == 'llm' and len(engine.analysis) == analysis+1
        assert len(engine.native) == generated


def test_native_classroom_repair_is_not_supported_by_a_generic_family_leave():
    raw = '尊敬的老师：您好，因明天需要参加家里的活动，我将无法正常上课，敬请谅解。'
    with closing(MemoryStore(':memory:')) as memory:
        engine = Replies([raw, raw])
        result = Avatar(memory=memory, llm=engine, capability_contract_enabled=True).respond(
            '帮我写一封请假邮件，我明天要参加家里的活动，只给正文。')
        assert '上课' not in result['reply'] and '老师' not in result['reply']
        assert result['generation_mode'] == 'rules_writing_artifact'
        assert len(engine.native) == 2
