import asyncio
import time
import pytest
from avatar.channels.qq.protocol import parse_event, IgnoredEvent
from avatar.channels.qq.bridge import QQBridge
from avatar.channels.qq.engine import AvatarEngine


def payload(text="我叫小林", *, user="user-a", group=None, mid="message-1", stamp=None):
    return {
        "t": "GROUP_AT_MESSAGE_CREATE" if group else "C2C_MESSAGE_CREATE",
        "d": {
            "id": mid,
            "timestamp": stamp or time.time(),
            "content": text,
            "author": {"member_openid": user} if group else {"user_openid": user},
            **({"group_openid": group} if group else {}),
        },
    }


def test_normalize_routes_and_reject_unsupported_input():
    m = parse_event("bot-1", payload(group="group-a"))
    assert m.target == "group-a" and m.user_id == "user-a" and m.kind == "group"
    assert m.context_key != parse_event("bot-1", payload()).context_key
    bad = payload()
    bad["t"] = "GROUP_MESSAGE_CREATE"
    with pytest.raises(IgnoredEvent):
        parse_event("bot-1", bad)
    bad = payload()
    bad["d"]["attachments"] = [{"url": "https://example.com/image"}]
    with pytest.raises(IgnoredEvent):
        parse_event("bot-1", bad)


def test_duplicate_is_not_generated_or_sent_twice(tmp_path):
    async def run():
        calls = []

        def generate(message, memory):
            calls.append(message.message_id)
            return "你好，小林。"

        bridge = QQBridge(tmp_path / "qq", engine=AvatarEngine(generate=generate))
        sent = []

        async def send(message, text):
            sent.append((message.target, text))

        try:
            message = parse_event("bot-1", payload())
            assert (await bridge.handle(message, send)).status == "sent"
            assert (await bridge.handle(message, send)).status == "sent"
            assert len(calls) == len(sent) == 1
        finally:
            await bridge.close()

    asyncio.run(run())


def test_conflicting_replay_and_send_failure_are_not_retried(tmp_path):
    async def run():
        bridge = QQBridge(
            tmp_path / "qq", engine=AvatarEngine(generate=lambda m, db: "回复内容")
        )
        sent = []

        async def fail(message, text):
            sent.append(text)
            raise RuntimeError("not-for-users")

        try:
            m = parse_event("bot-1", payload())
            assert (await bridge.handle(m, fail)).status == "delivery_unknown"
            assert (await bridge.handle(m, fail)).status == "delivery_unknown"
            assert len(sent) == 1
            changed = parse_event("bot-1", payload("替换成另一条消息"))
            assert (await bridge.handle(changed, fail)).status == "collision"
            assert len(sent) == 1
        finally:
            await bridge.close()

    asyncio.run(run())


def test_contexts_isolate_users_groups_bots_and_private_history(tmp_path):
    async def run():
        observed = []

        def generate(m, memory):
            observed.append(
                (m.context_key, memory.get_user_profile(), memory.get_short_term())
            )
            memory.remember_user("名字", m.text)
            memory.add_message("user", m.text, m.context_key)
            return "已经记住你的称呼。"

        bridge = QQBridge(tmp_path / "qq", engine=AvatarEngine(generate=generate))

        async def send(m, text):
            pass

        try:
            entries = [
                ("bot-1", payload("甲", mid="a")),
                ("bot-1", payload("乙", user="user-b", mid="b")),
                ("bot-1", payload("丙", group="g1", mid="c")),
                ("bot-1", payload("丁", group="g2", mid="d")),
                ("bot-2", payload("戊", mid="e")),
            ]
            for bot, event in entries:
                await bridge.handle(parse_event(bot, event), send)
            assert len({x[0] for x in observed}) == 5
            assert all(not profile and not history for _, profile, history in observed)
            await bridge.handle(parse_event("bot-1", payload("新称呼", mid="f")), send)
            assert observed[-1][1]["名字"] == "甲"
        finally:
            await bridge.close()

    asyncio.run(run())


def test_expired_event_is_not_processed(tmp_path):
    async def run():
        def generate(m, db):
            raise AssertionError("stale message processed")

        bridge = QQBridge(
            tmp_path / "qq", engine=AvatarEngine(generate=generate), clock=lambda: 1000
        )

        async def send(m, text):
            raise AssertionError("stale message sent")

        try:
            result = await bridge.handle(parse_event("bot-1", payload(stamp=1)), send)
            assert result.status == "expired"
        finally:
            await bridge.close()

    asyncio.run(run())


def test_generation_error_rolls_back_memory_before_retry(tmp_path):
    async def run():
        calls = []

        def generate(m, db):
            calls.append(1)
            db.remember_user("名字", "本轮名字")
            if len(calls) == 1:
                raise RuntimeError("provider-secret")
            return "你好，很高兴见到你。"

        bridge = QQBridge(tmp_path / "qq", engine=AvatarEngine(generate=generate))
        sent = []

        async def send(m, text):
            sent.append(text)

        m = parse_event("bot-1", payload())
        try:
            assert (await bridge.handle(m, send)).status == "generation_failed"
            from avatar.brain.memory import MemoryStore

            db = MemoryStore(
                str(tmp_path / "qq/contexts" / m.context_key / "memory.db")
            )
            try:
                assert db.get_user_profile() == {}
            finally:
                db.close()
            assert (await bridge.handle(m, send)).status == "sent"
            assert len(sent) == 1 and len(calls) == 2
        finally:
            await bridge.close()

    asyncio.run(run())


def test_restart_replays_ready_cache_but_not_unknown_send(tmp_path):
    async def run():
        calls = []
        bridge = QQBridge(
            tmp_path / "qq",
            engine=AvatarEngine(
                generate=lambda m, db: calls.append(1) or "缓存的回复内容"
            ),
        )
        ready = parse_event("bot-1", payload(mid="ready"))
        unknown = parse_event("bot-1", payload(mid="unknown"))
        assert bridge.generate(ready)[0] == "ready"
        assert bridge.generate(unknown)[0] == "ready"
        bridge.receipts.move(unknown.receipt_key, "ready", "sending", time.time())
        await bridge.close()
        new = QQBridge(
            tmp_path / "qq",
            engine=AvatarEngine(generate=lambda m, db: pytest.fail("must reuse cache")),
        )
        sent = []

        async def send(m, text):
            sent.append(text)

        try:
            assert (await new.handle(ready, send)).status == "sent"
            assert (await new.handle(unknown, send)).status == "delivery_unknown"
            assert len(sent) == 1 and len(calls) == 2
        finally:
            await new.close()

    asyncio.run(run())


def test_single_instance_and_async_other_user_progress(tmp_path):
    async def run():
        bridge = QQBridge(
            tmp_path / "qq",
            engine=AvatarEngine(generate=lambda m, db: "本轮回复内容"),
            workers=2,
            max_pending=2,
        )
        with pytest.raises(RuntimeError):
            QQBridge(tmp_path / "qq")
        entered = asyncio.Event()
        release = asyncio.Event()

        async def slow(m, text):
            entered.set()
            await release.wait()

        async def fast(m, text):
            pass

        first = asyncio.create_task(
            bridge.handle(parse_event("bot-1", payload()), slow)
        )
        try:
            await asyncio.wait_for(entered.wait(), 2)
            other = await asyncio.wait_for(
                bridge.handle(
                    parse_event("bot-1", payload(user="user-b", mid="second")), fast
                ),
                2,
            )
            assert other.status == "sent"
        finally:
            release.set()
            await first
            await bridge.close()

    asyncio.run(run())


def test_real_avatar_rules_and_history_are_scoped_and_restored(tmp_path):
    from avatar.brain.memory import MemoryStore

    class Offline:
        available = False

    async def run():
        bridge = QQBridge(tmp_path / "qq", engine=AvatarEngine(llm_factory=Offline))
        sent = []

        async def send(m, text):
            sent.append(text)

        m = parse_event("bot-1", payload("我叫小林"))
        try:
            await bridge.handle(m, send)
            await bridge.handle(parse_event("bot-1", payload("你好", mid="next")), send)
            db = MemoryStore(
                str(tmp_path / "qq/contexts" / m.context_key / "memory.db")
            )
            try:
                assert db.get_user_profile()["名字"] == "小林"
                assert (
                    db._conn.execute("SELECT count(*) FROM memory_messages").fetchone()[
                        0
                    ]
                    == 4
                )
                assert (
                    db._conn.execute("SELECT count(*) FROM qq_runtime").fetchone()[0]
                    == 1
                )
            finally:
                db.close()
            assert all(
                "LLM_API_KEY" not in text and "demo 模式" not in text for text in sent
            )
        finally:
            await bridge.close()

    asyncio.run(run())


def test_cancelled_generation_keeps_scope_locked_until_worker_finishes(tmp_path):
    import threading

    async def run():
        entered = threading.Event()
        release = threading.Event()

        def generate(m, db):
            entered.set()
            release.wait(3)
            return "生成完成的回复"

        bridge = QQBridge(tmp_path / "qq", engine=AvatarEngine(generate=generate))

        async def send(m, text):
            pytest.fail("cancelled handler must not send")

        message = parse_event("bot-1", payload())
        task = asyncio.create_task(bridge.handle(message, send))
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            task.cancel()
            await asyncio.sleep(0.01)
            assert bridge.pending == 1
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert bridge.pending == 0
            sent = []

            async def recovered(m, text):
                sent.append(text)

            assert (await bridge.handle(message, recovered)).status == "sent"
            assert len(sent) == 1
        finally:
            release.set()
            await bridge.close()

    asyncio.run(run())


def test_event_validation_and_reply_byte_limit():
    from avatar.channels.qq.protocol import bounded_reply
    import dataclasses

    assert len(bounded_reply("你好" * 2000).encode()) <= 3000
    assert bounded_reply("  你好  ") == "你好"
    with pytest.raises(ValueError):
        bounded_reply(" ")
    for stamp in (True, float("nan"), "2026-11-10T10:00:00"):
        with pytest.raises(IgnoredEvent):
            parse_event("bot-1", payload(stamp=stamp))


def test_credentials_stay_out_of_repr_and_invalid_state_root_is_rejected(monkeypatch):
    from avatar.channels.qq.nonebot_app import Settings, PROJECT

    secret = "offline-test-secret-123"
    monkeypatch.setenv("AVATAR_QQ_APP_ID", "12345678")
    monkeypatch.setenv("AVATAR_QQ_APP_SECRET", secret)
    monkeypatch.setenv("AVATAR_QQ_STATE_DIR", str(PROJECT / "data/qq-test-unused"))
    settings = Settings.environment()
    assert secret not in repr(settings)
    monkeypatch.setenv("AVATAR_QQ_STATE_DIR", "/outside-workspace")
    with pytest.raises(ValueError, match="workspace"):
        Settings.environment()


def test_missing_ready_cache_never_regenerates_a_reply(tmp_path):
    async def run():
        bridge = QQBridge(
            tmp_path / "qq", engine=AvatarEngine(generate=lambda m, db: "缓存回复")
        )
        message = parse_event("bot-1", payload(mid="ROBOT1.0_ab+/="))
        bridge.receipts.claim(message, time.time())
        bridge.receipts.move(message.receipt_key, "processing", "ready", time.time())

        async def send(m, text):
            pytest.fail("missing cache must not send")

        try:
            assert (await bridge.handle(message, send)).status == "generation_unknown"
            assert (await bridge.handle(message, send)).status == "generation_unknown"
        finally:
            await bridge.close()

    asyncio.run(run())
