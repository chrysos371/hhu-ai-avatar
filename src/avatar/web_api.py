"""Versioned management routing. HTTP/token boundaries remain in web.py."""

import json
import math
import os
import re
import time
import urllib.request
from .brain.admin_store import AdminStore, initial_persona
from .brain.operations import OperationService, OperationError
from .brain.persona import PersonaService
from .brain.emotion_overrides import EmotionOverrideService
from .brain.knowledge import KnowledgeService
from .brain.reminders import ReminderStore
from .brain.summaries import SummaryStore


def public(row):
    return {k: v for k, v in row.items() if k != "content_vector"} if row else None


class V1API:
    def __init__(self, server, memory, chat):
        self.server = server
        self.memory = memory
        self.chat = chat
        self.store = AdminStore(memory)
        self.store.migrate(initial_persona())
        self.ops = OperationService(self.store)

    def handle(self, post, path, query, data):
        get = lambda key, default=None: query.get(key, [default])[0]

        def integer(key, default=None):
            try:
                return int(get(key, default))
            except (ValueError, TypeError):
                raise OperationError(422, "invalid_pagination") from None

        if not post and path == "/system":
            from .config import config

            return 200, {
                "mode": "single-user-local",
                "backend": {"available": True},
                "model": {
                    "configured": bool(config.llm.api_key),
                    "available": None,
                    "reason": "未执行对话探测",
                },
                "counts": self.store.system_counts(),
                "legacy_writes_enabled": self.server.legacy_writes,
            }
        if not post and path == "/audit":
            return 200, self.store.list_audit(
                limit=integer("limit", 100),
                before_id=(
                    integer("before_id") if get("before_id") is not None else None
                ),
                operation_type=get("operation_type"),
                status=get("status"),
            )
        if not post and path == "/dashboard":
            state = self.server.emotion.state
            return 200, {
                "counts": self.store.system_counts(),
                "persona_version": self.store.current_persona()["id"],
                "emotion": {
                    "valence": state.valence,
                    "arousal": state.arousal,
                    "label": state.label(),
                },
                "energy": self.server.emotion.energy,
                "verification_rate": None,
                "verification_reason": "尚无独立语义验收统计",
                "recent_events": list(reversed(self.server.chat_events[-20:])),
                "audit": self.store.list_audit(limit=10),
            }
        if post and path == "/chat":
            text = data.get("text")
            use_web = data.get("use_web", False)
            if (
                not isinstance(text, str)
                or not 1 <= len(text.strip()) <= 4000
                or type(use_web) is not bool
            ):
                raise OperationError(422, "invalid_chat")
            result = self.chat(text, use_web)
            recalled = [
                public(self.memory.inspect(i)) for i in result.get("recalled_ids", [])
            ]
            result["trace"] = {
                "recalled_memories": [
                    {"id": r["id"], "content": r["content"], "status": r["status"]}
                    for r in recalled
                    if r
                ],
                "knowledge_sources": result.get("knowledge_sources", []),
                "knowledge_retrieval_degraded": result.get(
                    "knowledge_retrieval_degraded", False
                ),
                "decision": {
                    k: result.get(k)
                    for k in (
                        "strategy",
                        "style",
                        "user_emotion",
                        "emotion",
                        "user_valence",
                        "user_arousal",
                        "valence",
                        "arousal",
                    )
                },
                "guard": result.get("boundary"),
                "verifier": {
                    "available": False,
                    "reason": "未配置通用语义验证器",
                    "delivery_check": result.get("delivery_check"),
                },
                "tool_calls": [
                    {"tool": c.get("tool"), "status": c.get("status")}
                    for c in result.get("tool_calls", [])
                ],
            }
            self.server.chat_events.append(
                {
                    "timestamp": time.time(),
                    "strategy": result.get("strategy"),
                    "route": result.get("boundary", {}).get("route"),
                    "valence": result.get("valence"),
                    "arousal": result.get("arousal"),
                }
            )
            self.server.chat_events[:] = self.server.chat_events[-100:]
            return 200, result
        if not post and path == "/persona":
            return 200, PersonaService(self.store).current()
        if not post and path == "/persona/history":
            return 200, PersonaService(self.store).history()
        if post and path == "/persona/preview-chat":
            from .brain.admin_agent import ManagementTransport
            from .brain.boundaries import BOUNDARY_PROMPT

            if (
                set(data) != {"changes", "text"}
                or not isinstance(data["text"], str)
                or not 1 <= len(data["text"].strip()) <= 1000
            ):
                raise OperationError(422, "invalid_preview")
            svc = PersonaService(self.store)
            changes = data["changes"]
            if changes:
                svc.prepare({"changes": changes})
            elif not isinstance(changes, dict):
                raise OperationError(422, "invalid_preview")
            persona = svc.current()["data"] | changes
            try:
                raw = ManagementTransport().chat(
                    [
                        {
                            "role": "system",
                            "content": BOUNDARY_PROMPT
                            + '\n仅测试下述人设的表达，不激活、不记忆。输出JSON {"reply":"回复"}。人设数据：'
                            + json.dumps(persona, ensure_ascii=False),
                        },
                        {"role": "user", "content": data["text"]},
                    ]
                )
                reply = json.loads(raw)["reply"]
                if not isinstance(reply, str) or not 1 <= len(reply) <= 4000:
                    raise ValueError("invalid reply")
            except Exception:
                raise OperationError(
                    503,
                    "preview_unavailable",
                    "本地预览模型暂不可用；手动编辑和草案确认仍可使用。",
                ) from None
            return 200, {
                "reply": reply,
                "activated": False,
                "provider": "local",
                "scope": "expression-only",
            }
        if post and path == "/persona/draft":
            return 201, self.ops.create_draft("persona.update", data).data()
        if post and path == "/admin-agent/draft":
            from .brain.admin_agent import AdminAgent

            if not set(data) <= {"text", "allow_cloud"}:
                raise OperationError(422, "invalid_proposal")
            return 201, AdminAgent(self.store).propose(
                data.get("text"), allow_cloud=data.get("allow_cloud", False)
            )
        if not post and path == "/emotion":
            state = self.server.emotion.state
            active = EmotionOverrideService(self.store).active()
            return 200, {
                "automatic": {"valence": state.valence, "arousal": state.arousal},
                "user_observation": {
                    "valence": self.server.emotion.user_state.valence,
                    "arousal": self.server.emotion.user_state.arousal,
                },
                "effective": (
                    {k: active["data"][k] for k in ("valence", "arousal")}
                    if active
                    else {"valence": state.valence, "arousal": state.arousal}
                ),
                "override": active,
                "recent_observations": self.server.chat_events[-30:],
            }
        if post and path == "/emotion/draft":
            return 201, self.ops.create_draft("emotion.override", data).data()
        if not post and path == "/memory":
            history = get("history", "0")
            if history not in ("0", "1"):
                raise OperationError(422, "invalid_filter")
            rows = self.memory.recall(
                query=get("q", ""),
                memory_type=get("type"),
                include_history=history == "1",
                limit=5000,
            )
            if get("status") is not None:
                rows = [r for r in rows if r["status"] == get("status")]
            if get("since") is not None:
                since = float(get("since"))
                if not math.isfinite(since):
                    raise OperationError(422, "invalid_filter")
                rows = [r for r in rows if r["created_at"] >= since]
            result = []
            for r in rows:
                sources = self.store.conn.execute(
                    "SELECT evidence,source_message_id FROM memory_sources WHERE fragment_id=?",
                    (r["id"],),
                ).fetchall()
                confirmation = (
                    "manual_correction"
                    if any(s["evidence"] == "manual correction" for s in sources)
                    else (
                        "source_backed"
                        if any(s["source_message_id"] is not None for s in sources)
                        else "unrecorded"
                    )
                )
                result.append(
                    public(r)
                    | {
                        "strength": self.memory.memory_strength(r),
                        "confirmation_status": confirmation,
                    }
                )
            if get("confirmation") is not None:
                if get("confirmation") not in (
                    "manual_correction",
                    "source_backed",
                    "unrecorded",
                ):
                    raise OperationError(422, "invalid_filter")
                result = [
                    r for r in result if r["confirmation_status"] == get("confirmation")
                ]
            return 200, result
        match = re.fullmatch(r"/memory/(\d+)", path)
        if not post and match:
            row = public(self.memory.inspect(int(match[1])))
            if not row:
                raise OperationError(404, "memory_not_found")
            return 200, row
        if post and path == "/memory/batch-draft":
            return 201, self.ops.create_draft("memory.batch", data).data()
        if not post and path == "/summary":
            return 200, SummaryStore(self.memory).read(self.server.session_id)
        if not post and path == "/reminders":
            return 200, ReminderStore(self.memory).list()
        if post and path == "/reminders":
            return (
                201,
                self.ops.create_draft(
                    "memory.batch",
                    {
                        "actions": [
                            {"action": "reminder.create", "text": data.get("text")}
                        ]
                    },
                ).data(),
            )
        match = re.fullmatch(r"/reminders/(\d+)/(status-draft|delete-draft)", path)
        if post and match:
            a = {
                "id": int(match[1]),
                "action": (
                    "reminder.status"
                    if match[2] == "status-draft"
                    else "reminder.delete"
                ),
            }
            if match[2] == "status-draft":
                a["status"] = data.get("status")
            return 201, self.ops.create_draft("memory.batch", {"actions": [a]}).data()
        match = re.fullmatch(r"/summary/(\d+)/forget-draft", path)
        if post and match:
            return (
                201,
                self.ops.create_draft(
                    "memory.batch",
                    {
                        "actions": [
                            {
                                "action": "summary.forget",
                                "id": int(match[1]),
                                "session_id": self.server.session_id,
                            }
                        ]
                    },
                ).data(),
            )
        if post and path == "/reminders/due":
            return 200, ReminderStore(self.memory).claim_due()
        if not post and path == "/knowledge/sources":
            return 200, [
                dict(r)
                for r in self.store.conn.execute(
                    "SELECT id,title,sha256,created_at FROM knowledge_sources ORDER BY id DESC LIMIT 500"
                )
            ]
        if not post and path == "/knowledge/search":
            return 200, KnowledgeService(self.store).search(
                get("q", ""), limit=integer("limit", 8)
            )
        if post and path == "/knowledge/preview-text":
            if set(data) != {"title", "text"}:
                raise OperationError(422, "invalid_knowledge")
            draft = self.ops.create_draft("knowledge.import", data).data()
            preview = json.loads(
                self.store.conn.execute(
                    "SELECT parameters_json FROM operation_drafts WHERE id=?",
                    (draft["draft_id"],),
                ).fetchone()[0]
            )["prepared_preview"]
            return 201, {"preview": preview, "draft": draft}
        if post and path == "/operations/draft":
            if set(data) != {"operation_type", "parameters"}:
                raise OperationError(422, "invalid_operation")
            return (
                201,
                self.ops.create_draft(
                    data["operation_type"], data["parameters"]
                ).data(),
            )
        match = re.fullmatch(r"/operations/(\d+)", path)
        if not post and match:
            return 200, self.ops.preview(int(match[1])).data()
        match = re.fullmatch(r"/operations/(\d+)/confirm", path)
        if post and match:
            if set(data) != {"confirmation_token"}:
                raise OperationError(403, "invalid_confirmation_token")
            return 200, self.ops.confirm(int(match[1]), data["confirmation_token"])
        match = re.fullmatch(r"/audit/(\d+)/reverse-draft", path)
        if post and match:
            return 201, self.ops.create_reverse_draft(int(match[1])).data()
        if not post and path == "/tools/health":
            return 200, self.health()
        raise OperationError(404, "not_found")

    def health(self):
        rows = [
            {"name": n, "configured": True, "available": True, "last_error": None}
            for n in ("SQLite", "提醒", "知识")
        ]
        model = os.getenv("AVATAR_ADMIN_LOCAL_MODEL", "qwen3:4b")
        try:
            with urllib.request.urlopen(
                "http://127.0.0.1:11434/api/tags", timeout=0.7
            ) as response:
                raw = response.read(262145)
                if len(raw) > 262144:
                    raise ValueError("large response")
                tags = json.loads(raw).get("models", [])
            available = any(t.get("name") == model for t in tags)
            rows.append(
                {
                    "name": "本地管理模型",
                    "configured": True,
                    "available": available,
                    "last_error": (
                        None if available else "服务可连接，但指定模型尚未安装"
                    ),
                }
            )
        except Exception:
            rows.append(
                {
                    "name": "本地管理模型",
                    "configured": True,
                    "available": False,
                    "last_error": "本地Ollama服务暂不可用；手动编辑仍可使用",
                }
            )
        rows.append(
            {
                "name": "联网与天气",
                "configured": True,
                "available": None,
                "last_error": "未主动联网探测，调用时记录结果",
            }
        )
        return rows
