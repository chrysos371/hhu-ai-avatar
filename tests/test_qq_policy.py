import asyncio
from datetime import datetime, timezone
import pytest
from avatar.channels.qq.policy import ReplyPolicy, EXPRESSION_HINT
from avatar.channels.qq.bridge import QQBridge
from avatar.channels.qq.engine import AvatarEngine
from avatar.channels.qq.protocol import Incoming
from avatar.brain.context_budget import ContextBudget


def test_group_budget_shared_by_users_persistent_and_before_generation(tmp_path):
    async def run():
        now = [1000000.]
        calls, sends = [], []
        policy = ReplyPolicy(group_cooldown=2, group_per_minute=2)
        def message(mid, user='a', group='g', kind='group'):
            return Incoming('bot', kind, user, group, mid, '你好', now[0])
        def generate(m, db):
            calls.append(m.message_id)
            return '你好'
        async def send(m, reply):
            sends.append(m.message_id)
        bridge = QQBridge(tmp_path, engine=AvatarEngine(generate=generate),
                          clock=lambda: now[0], policy=policy)
        first = message('one')
        assert (await bridge.handle(first, send)).status == 'sent'
        assert (await bridge.handle(first, send)).status == 'sent'
        assert (await bridge.handle(message('two', 'b'), send)).status == 'rate_limited'
        now[0] += 3
        assert (await bridge.handle(message('three', 'b'), send)).status == 'sent'
        await bridge.close()
        bridge = QQBridge(tmp_path, engine=AvatarEngine(generate=generate),
                          clock=lambda: now[0], policy=policy)
        try:
            now[0] += 3
            assert (await bridge.handle(message('four', 'c'), send)).status == 'rate_limited'
            assert (await bridge.handle(message('five', group='other'), send)).status == 'sent'
            assert (await bridge.handle(message('private', kind='private'), send)).status == 'sent'
            assert calls == sends == ['one', 'three', 'five', 'private']
        finally:
            await bridge.close()
    asyncio.run(run())


def test_quiet_hours_timezone_wrap_and_invalid_configuration():
    policy = ReplyPolicy(quiet_start=23, quiet_end=7)
    def stamp(hour):
        return datetime(2026, 11, 10, hour, tzinfo=timezone.utc).timestamp()
    assert policy.quiet(stamp(16))  # midnight UTC+8
    assert not policy.quiet(stamp(0))
    assert not ReplyPolicy().quiet(stamp(16))
    for options in ({'quiet_start': 5}, {'quiet_start': 5, 'quiet_end': 5},
                    {'group_per_minute': 0}, {'group_cooldown': -1}):
        with pytest.raises(ValueError):
            ReplyPolicy(**options)


def test_context_keeps_whole_records_and_contiguous_recent_history():
    budget = ContextBudget()
    assert budget.items(['很长' * 3000, '有效事实'], 100) == ['有效事实']
    messages = [{'role': 'user', 'content': '旧消息'},
                {'role': 'assistant', 'content': '长' * 5000},
                {'role': 'user', 'content': '最新纠正'}]
    assert budget.history(messages) == messages[-1:]
    profile, facts, reminders, summary = budget.data(
        {'过长': '字' * 5000, '名字': '小林'}, ['事实'], [], ['线索'])
    assert profile == {'名字': '小林'} and facts == ['事实']
    assert '先给可直接使用的产物' in EXPRESSION_HINT


def test_actual_qq_prompt_preserves_current_input_and_safety(tmp_path):
    class FakeLLM:
        available = True
        def __init__(self):
            self.messages = None
        def chat_analysis(self, messages, **kwargs):
            return '{}'
        def chat(self, messages, **kwargs):
            self.messages = messages
            return '祝你生日快乐！'
    llm = FakeLLM()
    engine = AvatarEngine(llm_factory=lambda: llm)
    message = Incoming('bot', 'private', 'a', 'a', 'prompt',
                       '帮我写一句生日祝福', 1000000.)
    engine.respond(message, tmp_path)
    assert llm.messages[-1] == {'role': 'user', 'content': message.text}
    assert sum(m['content'] == message.text for m in llm.messages) == 1
    assert 'QQ表达约束' in llm.messages[0]['content']
    assert '没有真实身体' in llm.messages[0]['content']
    assert len(llm.messages[0]['content']) <= 16000


def test_quiet_group_does_not_generate_but_private_still_responds(tmp_path):
    async def run():
        now = datetime(2026, 11, 10, 16, tzinfo=timezone.utc).timestamp()
        calls = []
        def generate(m, db):
            calls.append(m.kind)
            return '你好'
        async def send(m, text):
            pass
        bridge = QQBridge(tmp_path, engine=AvatarEngine(generate=generate),
                          clock=lambda: now, policy=ReplyPolicy(quiet_start=23, quiet_end=7))
        try:
            group = Incoming('bot', 'group', 'a', 'g', 'g1', '你好', now)
            private = Incoming('bot', 'private', 'a', 'a', 'p1', '你好', now)
            assert (await bridge.handle(group, send)).status == 'quiet_hours'
            assert (await bridge.handle(private, send)).status == 'sent'
            assert calls == ['private']
        finally:
            await bridge.close()
    asyncio.run(run())


def test_missing_or_failed_model_reports_outage_not_fake_listening(tmp_path, caplog):
    class Missing:
        available = False
    class Broken:
        available = True
        def chat_analysis(self, *args, **kwargs):
            raise RuntimeError('test failure')
        def chat(self, *args, **kwargs):
            raise RuntimeError('test failure')
    for name, llm in [('missing', Missing()), ('broken', Broken())]:
        engine = AvatarEngine(llm_factory=lambda: llm)
        message = Incoming('bot', 'private', 'a', 'a', name, '23加19是多少', 1000000.)
        reply = engine.respond(message, tmp_path / name)
        assert '暂时无法生成' in reply
        assert '继续说' not in reply
    assert 'model_unconfigured' in caplog.text
    assert 'model_reply_failed' in caplog.text


def test_degraded_replies_are_audited_but_not_restored_as_conversation(tmp_path):
    from avatar.brain.memory import MemoryStore
    class Missing:
        available = False
    message = Incoming('bot', 'private', 'a', 'a', 'bad', '我叫小林', 1000000.)
    AvatarEngine(llm_factory=Missing).respond(message, tmp_path)
    class Good:
        available = True
        def chat_analysis(self, messages, **kwargs):
            self.analysis = messages
            return '{}'
        def chat(self, messages, **kwargs):
            self.reply = messages
            return '你好，小林。'
    good = Good()
    next_message = Incoming('bot', 'private', 'a', 'a', 'good', '你好', 1000001.)
    AvatarEngine(llm_factory=lambda: good).respond(next_message, tmp_path)
    for messages in (good.analysis, good.reply):
        assert not any('暂时无法生成' in m['content'] for m in messages)
        assert any(m['content'] == '我叫小林' for m in messages)
    store = MemoryStore(str(tmp_path / 'memory.db'))
    try:
        assert store.get_user_profile()['名字'] == '小林'
        assert store._conn.execute('SELECT count(*) FROM qq_degraded_messages').fetchone()[0] == 1
        metrics = store._conn.execute('SELECT total_ms,analysis_ms,degraded FROM qq_turn_metrics ORDER BY created_at').fetchall()
        assert len(metrics) == 2 and [m['degraded'] for m in metrics] == [1,0]
        assert all(m['total_ms'] >= m['analysis_ms'] >= 0 for m in metrics)
        assert store._conn.execute("SELECT count(*) FROM memory_messages WHERE content LIKE '%暂时无法生成%'").fetchone()[0] == 1
    finally:store.close()


def test_qq_keeps_boundary_prefix_stable_when_strategy_changes(tmp_path):
    from avatar.brain.boundaries import BOUNDARY_PROMPT
    class Fake:
        available = True
        def __init__(self):self.prompts=[]
        def chat_analysis(self, *args, **kwargs):return '{}'
        def chat(self, messages, **kwargs):
            self.prompts.append(messages[0]['content'])
            return '好的。'
    llm = Fake()
    engine = AvatarEngine(llm_factory=lambda: llm)
    for i,text in enumerate(['只想听我说，不要给建议', '我先走了，拜拜']):
        engine.respond(Incoming('bot','private','a','a',str(i),text,1000000.+i), tmp_path)
    prefixes = [p[:p.index(BOUNDARY_PROMPT)+len(BOUNDARY_PROMPT)] for p in llm.prompts]
    assert prefixes[0] == prefixes[1]
