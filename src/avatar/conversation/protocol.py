from dataclasses import dataclass
import hashlib
import json

@dataclass(frozen=True)
class TurnRequest:
    channel: str
    bot_id: str
    kind: str
    user_id: str
    target: str
    message_id: str
    text: str
    occurred_at: float
    storage_namespace: str | None = None

    def _key(self, values):
        return hashlib.sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()

    @property
    def context_key(self):
        return self._key([self.storage_namespace or self.channel, self.bot_id, self.kind, self.target, self.user_id])

    @property
    def receipt_key(self):
        return self._key([self.channel, self.bot_id, self.kind, self.message_id])

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
