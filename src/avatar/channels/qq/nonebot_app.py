"""Optional NoneBot QQ bridge. Importing this module never logs in or sends."""

from __future__ import annotations
from dataclasses import dataclass, field
import os
import logging
from pathlib import Path
from .bridge import QQBridge
from .protocol import IgnoredEvent, parse_event

PROJECT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class Settings:
    app_id: str
    secret: str = field(repr=False)
    root: Path = PROJECT / "data/qq"

    @classmethod
    def environment(cls):
        from ...config import (
            config,
        )  # Load the project's dotenv without changing its settings.

        app = os.getenv("AVATAR_QQ_APP_ID", "").strip()
        secret = os.getenv("AVATAR_QQ_APP_SECRET", "").strip()
        if (
            not app
            or not secret
            or not app.isascii()
            or not app.isdigit()
            or len(app) > 30
            or not 8 <= len(secret) <= 256
        ):
            raise ValueError(
                "Configure AVATAR_QQ_APP_ID and AVATAR_QQ_APP_SECRET locally"
            )
        root = Path(
            os.getenv("AVATAR_QQ_STATE_DIR", str(PROJECT / "data/qq"))
        ).resolve()
        if not root.is_relative_to(PROJECT.parent):
            raise ValueError("QQ state must stay inside the workspace")
        return cls(app, secret, root)


def register(settings, *, bridge_factory=QQBridge):
    import nonebot
    from nonebot.adapters.qq import Adapter, Bot
    from nonebot.adapters.qq.event import (
        C2CMessageCreateEvent,
        GroupAtMessageCreateEvent,
    )
    from nonebot.adapters.qq.config import Intents
    from nonebot.adapters import Event

    # Only official outbound WebSocket transport; no public HTTP/admin port is exposed.
    intent = {key: False for key in Intents.model_fields}
    intent["c2c_group_at_messages"] = True
    nonebot.init(
        driver="~httpx+~websockets",
        log_level="WARNING",
        qq_bots=[
            {
                "id": settings.app_id,
                "secret": settings.secret,
                "intent": intent,
                "use_websocket": True,
            }
        ],
        qq_api_base="https://api.bot.qq.com/",
        qq_auth_base="https://api.bot.qq.com/app/getAppAccessToken",
    )
    driver = nonebot.get_driver()
    driver.register_adapter(Adapter)
    # Local imports must be resolvable by NoneBot's runtime dependency inspection.
    bridge = bridge_factory(settings.root)
    matcher = nonebot.on_type(
        (C2CMessageCreateEvent, GroupAtMessageCreateEvent), priority=10, block=True
    )

    async def handle(bot: Bot, event: Event):
        if bot.self_id != settings.app_id:
            return
        message = event.get_message()
        if any(segment.type != "text" for segment in message):
            return
        try:
            body = {
                "id": event.id,
                "timestamp": event.timestamp,
                "content": event.get_plaintext(),
                "author": event.author.model_dump(),
                "attachments": getattr(event, "attachments", None),
            }
            if isinstance(event, GroupAtMessageCreateEvent):
                body["group_openid"] = event.group_openid
            incoming = parse_event(bot.self_id, {"t": event.__type__.value, "d": body})
        except (IgnoredEvent, ValueError, AttributeError, TypeError):
            return

        async def send(receipt, text):
            # Bot.send routes against this authenticated SDK event, never LLM-provided IDs.
            await bot.send(event, text)

        try:
            outcome = await bridge.handle(incoming, send)
        except Exception as exc:
            logging.getLogger(__name__).error(
                "QQ processing failed type=%s receipt=%s",
                type(exc).__name__,
                incoming.receipt_key[:12],
            )
            return
        if outcome.status not in ("sent", "duplicate"):
            logging.getLogger(__name__).warning(
                "QQ event status=%s receipt=%s",
                outcome.status,
                outcome.receipt_key[:12],
            )

    # Replace postponed local annotations with the actual optional SDK classes.
    handle.__annotations__ = {"bot": Bot, "event": Event}
    matcher.append_handler(handle)
    driver.on_shutdown(bridge.close)
    return driver, bridge, handle


def run():
    import nonebot

    settings = Settings.environment()
    register(settings)
    nonebot.run()
