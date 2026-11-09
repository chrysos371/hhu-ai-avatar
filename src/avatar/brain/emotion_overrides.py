"""Timed expression overrides; never edit observed or automatic emotion history."""

import json
import math
import time
from .admin_store import canonical_json


class EmotionOverrideService:
    def __init__(self, store):
        self.s = store

    def active(self, now=None):
        now = time.time() if now is None else now
        row = self.s.conn.execute(
            "SELECT * FROM emotion_overrides WHERE status='active' AND starts_at<=? AND expires_at>? ORDER BY id DESC LIMIT 1",
            (now, now),
        ).fetchone()
        return (
            dict(
                id=row["id"],
                data=json.loads(row["data_json"]),
                starts_at=row["starts_at"],
                expires_at=row["expires_at"],
            )
            if row
            else None
        )

    def snapshot(self, p):
        row = self.s.conn.execute(
            "SELECT id FROM emotion_overrides ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return {"version": row["id"] if row else 0, "active": self.active()}

    def prepare(self, p):
        if p.get("clear") is True:
            if set(p) != {"clear", "reason"}:
                raise ValueError("invalid clear")
        else:
            if (
                set(p) != {"values", "duration_seconds", "reason"}
                or not isinstance(p["values"], dict)
                or set(p["values"]) != {"valence", "arousal"}
            ):
                raise ValueError("invalid override")
            if (
                type(p["duration_seconds"]) is not int
                or not 30 <= p["duration_seconds"] <= 86400
            ):
                raise ValueError("invalid duration")
            if any(
                type(v) not in (int, float) or not math.isfinite(v) or not -1 <= v <= 1
                for v in p["values"].values()
            ):
                raise ValueError("invalid PAD")
        if not isinstance(p["reason"], str) or not 1 <= len(p["reason"].strip()) <= 500:
            raise ValueError("reason required")
        b = self.snapshot(p)
        return (
            b,
            [{"field": "expression_override", "before": b["active"], "after": p}],
            ["只覆盖角色表达，不修改用户观测或自动状态；到期后自动恢复。"],
        )

    def execute(self, p):
        now = time.time()
        clear = p.get("clear") is True
        self.s.conn.execute(
            "UPDATE emotion_overrides SET status='replaced' WHERE status='active'"
        )
        self.s.conn.execute(
            "INSERT INTO emotion_overrides(data_json,starts_at,expires_at,status) VALUES(?,?,?,?)",
            (
                canonical_json({**p.get("values", {}), "reason": p["reason"]}),
                now,
                now if clear else now + p["duration_seconds"],
                "cleared" if clear else "active",
            ),
        )
        return self.snapshot(p)

    def draft(self, values, duration_seconds, reason):
        from .operations import OperationService

        return OperationService(self.s).create_draft(
            "emotion.override",
            dict(values=values, duration_seconds=duration_seconds, reason=reason),
        )

    def reverse(self, before, after):
        from .operations import OperationError

        if self.snapshot({})["version"] != after["version"]:
            raise OperationError(409, "stale_reverse")
        active = before.get("active")
        remaining = int(active["expires_at"] - time.time()) if active else 0
        if remaining < 30:
            return {"clear": True, "reason": "恢复此前无有效覆盖的状态"}
        return {
            "values": {k: active["data"][k] for k in ("valence", "arousal")},
            "duration_seconds": min(remaining, 86400),
            "reason": "恢复此前覆盖",
        }
