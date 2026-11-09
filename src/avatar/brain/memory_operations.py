"""Batch adapter delegates all memory mutation to existing version/trust methods."""

import hashlib


class MemoryBatchExecutor:
    def __init__(self, store):
        self.s = store
        self.m = store.memory

    def snapshot(self, p):
        items = []
        for action in p["actions"]:
            if action["action"].startswith("reminder."):
                from .reminders import ReminderStore

                rows = ReminderStore(self.m).list()
                if action["action"] == "reminder.create":
                    import time

                    items.append(
                        {
                            "reminders": rows,
                            "deadline_passed": action.get(
                                "resolved_due_at", float("inf")
                            )
                            <= time.time(),
                        }
                    )
                else:
                    items.append(
                        next((r for r in rows if r["id"] == action["id"]), None)
                    )
                continue
            if action["action"] == "summary.forget":
                row = self.s.conn.execute(
                    "SELECT id,content FROM memory_messages WHERE id=?", (action["id"],)
                ).fetchone()
                items.append(
                    {
                        "id": row["id"],
                        "content_sha256": hashlib.sha256(
                            row["content"].encode()
                        ).hexdigest(),
                    }
                    if row
                    else None
                )
                continue
            row = self.m.inspect(action["id"])
            items.append(
                (
                    {
                        k: row.get(k)
                        for k in (
                            "id",
                            "status",
                            "predecessor_id",
                            "valid_from",
                            "valid_to",
                        )
                    }
                    | {
                        "content_sha256": hashlib.sha256(
                            row["content"].encode()
                        ).hexdigest()
                    }
                )
                if row
                else None
            )
        return {"context_revision": self.m.context_revision, "items": items}

    def prepare(self, p):
        if (
            set(p) != {"actions"}
            or not isinstance(p["actions"], list)
            or not 1 <= len(p["actions"]) <= 100
        ):
            raise ValueError("invalid batch")
        seen = set()
        diff = []
        warnings = []
        for a in p["actions"]:
            if isinstance(a, dict) and a.get("action") in (
                "reminder.create",
                "reminder.status",
                "reminder.delete",
                "summary.forget",
            ):
                from .reminders import ReminderStore, parse_reminder

                kind = a["action"]
                fields = (
                    {"action", "text"}
                    if kind == "reminder.create"
                    else (
                        {"action", "id", "status"}
                        if kind == "reminder.status"
                        else (
                            {"action", "id", "session_id"}
                            if kind == "summary.forget"
                            else {"action", "id"}
                        )
                    )
                )
                if set(a) != fields:
                    raise ValueError("invalid action fields")
                if kind == "reminder.create":
                    if (
                        not isinstance(a["text"], str)
                        or not 1 <= len(a["text"]) <= 4000
                        or parse_reminder(a["text"]) is None
                    ):
                        raise ValueError("invalid reminder")
                    import time

                    a["resolved_at"] = time.time()
                    a["resolved_due_at"] = parse_reminder(
                        a["text"], now=a["resolved_at"]
                    )["due_at"]
                    before = None
                else:
                    if type(a["id"]) is not int or a["id"] <= 0:
                        raise ValueError("invalid id")
                    if kind == "summary.forget":
                        if (
                            not isinstance(a["session_id"], str)
                            or not 1 <= len(a["session_id"]) <= 128
                        ):
                            raise ValueError("invalid session")
                        row = self.s.conn.execute(
                            "SELECT id FROM memory_messages WHERE id=?", (a["id"],)
                        ).fetchone()
                        if not row:
                            raise ValueError("missing source")
                        before = {"id": a["id"]}
                    else:
                        before = next(
                            (
                                r
                                for r in ReminderStore(self.m).list()
                                if r["id"] == a["id"]
                            ),
                            None,
                        )
                        if before is None:
                            raise ValueError("missing reminder")
                    if kind == "reminder.status" and a["status"] not in (
                        "cancelled",
                        "completed",
                    ):
                        raise ValueError("invalid status")
                diff.append({"field": kind, "before": before, "after": a})
                if kind in ("summary.forget", "reminder.delete"):
                    warnings.append("此删除不可撤销。")
                continue
            if not isinstance(a, dict) or a.get("action") not in (
                "correct",
                "forget",
                "badhit",
            ):
                raise ValueError("invalid action")
            required = (
                {"id", "action", "content"}
                if a["action"] == "correct"
                else {"id", "action"}
            )
            if set(a) != required or type(a["id"]) is not int or a["id"] <= 0:
                raise ValueError("invalid action fields")
            row = self.m.inspect(a["id"])
            if not row:
                raise ValueError("memory not found")
            chain = set(self.m._version_ids(a["id"]))
            if chain & seen:
                raise ValueError("overlapping version chains")
            seen |= chain
            if a["action"] == "correct" and (
                row["status"] != "active"
                or not isinstance(a["content"], str)
                or not 1 <= len(a["content"].strip()) <= 4000
            ):
                raise ValueError("invalid correction")
            diff.append(
                {
                    "field": f"memory.{a['id']}",
                    "before": row["content"],
                    "after": (
                        a.get("content") if a["action"] == "correct" else a["action"]
                    ),
                }
            )
            if a["action"] == "forget":
                warnings.append(
                    f"彻底删除记忆{a['id']}及其{len(chain)}个相关版本，不可撤销；共享原话会脱敏。"
                )
        return self.snapshot(p), diff, warnings

    def execute(self, p):
        results = []
        for a in p["actions"]:
            if a["action"].startswith("reminder."):
                from .reminders import ReminderStore

                store = ReminderStore(self.m)
                if a["action"] == "reminder.create":
                    result = store.create(a["text"], now=a["resolved_at"])
                elif a["action"] == "reminder.status":
                    store.set_status(a["id"], a["status"])
                    result = {"id": a["id"], "status": a["status"]}
                else:
                    store.delete(a["id"])
                    result = {"deleted_id": a["id"]}
                results.append({"action": a["action"], "result": result})
                continue
            if a["action"] == "summary.forget":
                from .summaries import SummaryStore

                SummaryStore(self.m).forget_source(a["session_id"], a["id"])
                results.append({"action": a["action"], "source_id": a["id"]})
                continue
            new_id = None
            if a["action"] == "correct":
                new_id = self.m.correct(a["id"], a["content"])
            elif a["action"] == "forget":
                self.m.forget(a["id"])
            else:
                self.m.report_irrelevant(a["id"])
            results.append(dict(action=a["action"], old_id=a["id"], new_id=new_id))
        return {"actions": results}

    def reverse(self, before, after):
        from .operations import OperationError

        if any(a["action"] != "correct" for a in after["actions"]):
            raise OperationError(422, "not_reversible")
        actions = []
        for a in after["actions"]:
            old = self.m.inspect(a["old_id"])
            if old is None:
                raise OperationError(422, "not_reversible")
            actions.append(
                dict(action="correct", id=a["new_id"], content=old["content"])
            )
        return {"actions": actions}
