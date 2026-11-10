"""Optional real-SDK contract test. No connection startup or real QQ send."""

import asyncio
from datetime import datetime, timezone
import pytest


def test_official_sdk_private_and_group_events_route_and_deduplicate(
    tmp_path, monkeypatch
):
    pytest.importorskip("nonebot")
    from nonebot.adapters.qq.event import (
        C2CMessageCreateEvent,
        GroupAtMessageCreateEvent,
    )
    from avatar.channels.qq.nonebot_app import Settings, register
    from avatar.channels.qq.bridge import QQBridge
    from avatar.channels.qq.engine import AvatarEngine
    import urllib.request

    def no_network(*args, **kwargs):
        raise AssertionError("No network in SDK contract test")

    monkeypatch.setattr(urllib.request, "urlopen", no_network)

    async def run():
        _, bridge, handle = register(
            Settings("12345678", "offline-dummy-secret", tmp_path / "qq"),
            bridge_factory=lambda root: QQBridge(
                root, engine=AvatarEngine(generate=lambda m, db: "离线接口验证回复")
            ),
        )

        class Bot:
            self_id = "12345678"

            def __init__(self):
                self.sent = []

            async def send(self, event, text):
                self.sent.append((event.id, text))

        bot = Bot()
        stamp = datetime.now(timezone.utc).isoformat()
        private = C2CMessageCreateEvent.model_validate(
            {
                "id": "p-1",
                "content": "你好",
                "timestamp": stamp,
                "author": {"id": "private-target", "user_openid": "private-user"},
            }
        )
        group = GroupAtMessageCreateEvent.model_validate(
            {
                "id": "g-1",
                "content": "你好",
                "timestamp": stamp,
                "author": {
                    "id": "group-user",
                    "bot": False,
                    "member_openid": "group-user",
                    "member_role": "member",
                },
                "group_id": "internal-group",
                "group_openid": "group-target",
            }
        )
        try:
            await handle(bot, private)
            await handle(bot, private)
            await handle(bot, group)
            assert [r[0] for r in bot.sent] == ["p-1", "g-1"]
            assert (
                str(type(__import__("nonebot").get_driver()).__name__)
                == "CombinedDriver"
            )
        finally:
            await bridge.close()

    asyncio.run(run())
