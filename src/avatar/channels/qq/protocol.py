from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
import re


class IgnoredEvent(ValueError):
    """Unsupported or invalid event. Never echo its raw payload to logs."""


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()


def identifier(value, *, message=False):
    pattern = r"[A-Za-z0-9_.:+=/-]{1,512}" if message else r"[A-Za-z0-9_.:+=-]{1,200}"
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise IgnoredEvent("invalid_identifier")
    return value


@dataclass(frozen=True)
class Incoming:
    bot_id: str
    kind: str
    user_id: str
    target: str
    message_id: str
    text: str
    occurred_at: float

    @property
    def context_key(self):
        return digest(["qq", self.bot_id, self.kind, self.target, self.user_id])

    @property
    def receipt_key(self):
        return digest(["qq", self.bot_id, self.kind, self.message_id])

    @property
    def fingerprint(self):
        return digest(
            [
                self.bot_id,
                self.kind,
                self.user_id,
                self.target,
                self.message_id,
                self.text,
                self.occurred_at,
            ]
        )


def parse_event(bot_id, payload):
    try:
        identifier(bot_id)
        if not isinstance(payload, dict) or payload.get("t") not in (
            "C2C_MESSAGE_CREATE",
            "GROUP_AT_MESSAGE_CREATE",
        ):
            raise IgnoredEvent("unsupported_event")
        data = payload["d"]
        author = data["author"]
        if data.get("attachments") or data.get("embeds") or author.get("bot") is True:
            raise IgnoredEvent("unsupported_media_or_bot")
        kind = "private" if payload["t"] == "C2C_MESSAGE_CREATE" else "group"
        user = identifier(
            author["user_openid"] if kind == "private" else author["member_openid"]
        )
        target = user if kind == "private" else identifier(data["group_openid"])
        content = data["content"]
        if (
            not isinstance(content, str)
            or not 1 <= len(content.strip()) <= 4000
            or "\x00" in content
        ):
            raise IgnoredEvent("invalid_text")
        stamp = data["timestamp"]
        if isinstance(stamp, datetime):
            if stamp.tzinfo is None:
                raise IgnoredEvent("timestamp_timezone_required")
            stamp = stamp.timestamp()
        elif isinstance(stamp, str):
            dt = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                raise IgnoredEvent("timestamp_timezone_required")
            stamp = dt.timestamp()
        if type(stamp) not in (int, float) or not math.isfinite(stamp) or stamp <= 0:
            raise IgnoredEvent("invalid_timestamp")
        return Incoming(
            bot_id,
            kind,
            user,
            target,
            identifier(data["id"], message=True),
            content.strip(),
            float(stamp),
        )
    except (ValueError, TypeError, KeyError, AttributeError):
        raise IgnoredEvent("unsupported_or_invalid_event") from None


def bounded_reply(text, limit=3000):
    if not isinstance(text, str) or not text.strip():
        raise ValueError("empty_reply")
    text = text.strip()
    if len(text.encode()) <= limit:
        return text
    suffix = "\n（回复较长，已截短。）"
    return (
        text.encode()[: limit - len(suffix.encode())].decode("utf-8", errors="ignore")
        + suffix
    )
