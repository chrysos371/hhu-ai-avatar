"""Outbound authenticated local OneBot WebSocket; import never connects."""
from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
from urllib.parse import urlsplit
from .bridge import QQBridge
from .onebot import parse_onebot, qq_number
from .protocol import IgnoredEvent

PROJECT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class Settings:
    account: str
    token: str = field(repr=False)
    url: str = 'ws://127.0.0.1:6700'
    root: Path = PROJECT / 'data/qq-onebot'

    def __post_init__(self):
        if not isinstance(self.account, str) or qq_number(self.account) != self.account:
            raise ValueError("OneBot account must be a canonical QQ number")
        url = urlsplit(self.url)
        if (url.scheme != 'ws' or url.hostname not in ('127.0.0.1', '::1')
                or url.username or url.password or url.query or url.fragment
                or url.port is None or not 1 <= url.port <= 65535):
            raise ValueError('OneBot requires a loopback WebSocket URL with explicit port')
        if not 16 <= len(self.token) <= 256 or any(c.isspace() for c in self.token):
            raise ValueError('OneBot requires a 16-256 character token without whitespace')
        if not Path(self.root).resolve().is_relative_to(PROJECT.parent):
            raise ValueError('OneBot state must stay inside workspace')

    @classmethod
    def environment(cls):
        from ...config import config  # Load local dotenv.
        return cls(os.getenv('AVATAR_ONEBOT_QQ', '').strip(),
                   os.getenv('AVATAR_ONEBOT_TOKEN', '').strip(),
                   os.getenv('AVATAR_ONEBOT_WS_URL', 'ws://127.0.0.1:6700').strip(),
                   Path(os.getenv('AVATAR_ONEBOT_STATE_DIR', str(PROJECT / 'data/qq-onebot'))))


async def dispatch(settings, bridge, bot, event):
    if str(bot.self_id) != settings.account:
        return
    try:
        body = event.model_dump()
        # SDK preprocessing removes @/reply segments; inspect original wire message.
        body['message'] = body['original_message']
        incoming = parse_onebot(settings.account, body)
    except IgnoredEvent:
        return
    from nonebot.adapters.onebot.v11 import Message, MessageSegment
    async def send(receipt, text):
        # Use explicit literal text segments: generated CQ codes cannot become actions/media.
        message = Message(MessageSegment.text(text))
        if incoming.kind == 'private':
            await bot.send_private_msg(user_id=int(incoming.user_id), message=message)
        else:
            await bot.send_group_msg(group_id=int(incoming.target), message=message)
    try:
        outcome = await bridge.handle(incoming, send)
        if outcome.status not in ('sent', 'duplicate'):
            logging.getLogger(__name__).warning('OneBot status=%s receipt=%s',
                                               outcome.status, incoming.receipt_key[:12])
        return outcome
    except Exception as exc:
        logging.getLogger(__name__).error('OneBot failure type=%s receipt=%s',
                                         type(exc).__name__, incoming.receipt_key[:12])


def register(settings, *, bridge_factory=QQBridge):
    import nonebot
    from nonebot.adapters.onebot.v11 import Adapter, Bot, MessageEvent
    nonebot.init(driver='~httpx+~websockets', log_level='WARNING',
                 onebot_v11_access_token=settings.token,
                 onebot_v11_ws_urls=[settings.url], api_timeout=20)
    driver = nonebot.get_driver()
    driver.register_adapter(Adapter)
    bridge = bridge_factory(settings.root)
    matcher = nonebot.on_type(MessageEvent, priority=10, block=True)
    async def handle(bot, event):
        return await dispatch(settings, bridge, bot, event)
    handle.__annotations__ = {'bot': Bot, 'event': MessageEvent}
    matcher.append_handler(handle)
    driver.on_shutdown(bridge.close)
    return driver, bridge, handle


def run():
    import nonebot
    register(Settings.environment())
    nonebot.run()
