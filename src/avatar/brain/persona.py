"""Immutable persona payloads; activation is only performed by confirmed drafts."""

import json
import math
import time
from .admin_store import canonical_json


FIELDS = {
    "name",
    "core_identity",
    "expression_principles",
    "relationship_boundaries",
    "immutable_rules",
    "temperature_bias",
    "initiative",
}


class PersonaService:
    def __init__(self, store):
        self.s = store

    def current(self):
        return self.s.current_persona()

    def history(self):
        return [
            self.s.persona_row(r)
            for r in self.s.conn.execute(
                "SELECT * FROM persona_versions ORDER BY id DESC LIMIT 200"
            )
        ]

    def snapshot(self, p):
        current = self.current()
        return {"id": current["id"], "data": current["data"]}

    def prepare(self, p):
        if (
            set(p) != {"changes"}
            or not isinstance(p["changes"], dict)
            or not p["changes"]
            or not set(p["changes"]) <= FIELDS
        ):
            raise ValueError("invalid persona")
        before = self.snapshot(p)
        for k, v in p["changes"].items():
            if k in ("temperature_bias", "initiative"):
                if (
                    type(v) not in (float, int)
                    or not math.isfinite(v)
                    or not (
                        (-0.5 <= v <= 0.5) if k == "temperature_bias" else (0 <= v <= 1)
                    )
                ):
                    raise ValueError("invalid number")
            elif (
                not isinstance(v, str)
                or not v.strip()
                or len(v) > (80 if k == "name" else 2000)
            ):
                raise ValueError("invalid persona text")
        diff = [
            {"field": k, "before": before["data"].get(k), "after": v}
            for k, v in sorted(p["changes"].items())
            if v != before["data"].get(k)
        ]
        if not diff:
            raise ValueError("no changes")
        return before, diff, ["系统事实与安全边界始终保留，人设不能覆盖它们。"]

    def execute(self, p):
        before = self.snapshot(p)
        data = {**before["data"], **p["changes"]}
        row = self.s.conn.execute(
            "INSERT INTO persona_versions(parent_id,data_json,created_at) VALUES(?,?,?)",
            (before["id"], canonical_json(data), time.time()),
        )
        self.s.conn.execute(
            "UPDATE admin_state SET value=? WHERE key='persona'", (str(row.lastrowid),)
        )
        self.s.memory._invalidate_context()
        return self.snapshot(p)

    def draft_update(self, changes):
        from .operations import OperationService

        return OperationService(self.s).create_draft(
            "persona.update", {"changes": changes}
        )

    def reverse(self, before, after):
        if self.current()["id"] != after["id"]:
            from .operations import OperationError

            raise OperationError(409, "stale_reverse")
        return {"changes": before["data"]}
