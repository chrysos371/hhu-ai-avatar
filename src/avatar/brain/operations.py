"""Typed admin drafts: one-time confirmation, optimistic baseline and atomic audit."""

from dataclasses import dataclass, asdict
import hashlib
import json
import secrets
import time
from typing import Literal

from .admin_store import canonical_json

OperationType = Literal[
    "persona.update", "emotion.override", "knowledge.import", "memory.batch"
]
ALLOWED = {"persona.update", "emotion.override", "knowledge.import", "memory.batch"}


class OperationError(ValueError):
    def __init__(self, status, code, message=None):
        self.status = status
        self.code = code
        self.message = message or code
        super().__init__(code)


@dataclass(frozen=True)
class OperationPreview:
    draft_id: int
    operation_type: str
    diff: tuple[dict, ...]
    warnings: tuple[str, ...]
    expires_at: float
    confirmation_token: str

    def data(self):
        return asdict(self)


class OperationService:
    def __init__(self, store, *, executors=None, clock=None):
        self.store = store
        self.conn = store.conn
        self.memory = store.memory
        self.clock = clock or time.time
        if executors is None:
            from .persona import PersonaService
            from .emotion_overrides import EmotionOverrideService
            from .knowledge import KnowledgeService
            from .memory_operations import MemoryBatchExecutor

            executors = {
                "persona.update": PersonaService(store),
                "emotion.override": EmotionOverrideService(store),
                "knowledge.import": KnowledgeService(store),
                "memory.batch": MemoryBatchExecutor(store),
            }
        self.executors = executors

    @staticmethod
    def _hash(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def _executor(self, kind):
        if (
            not isinstance(kind, str)
            or kind not in ALLOWED
            or kind not in self.executors
        ):
            raise OperationError(422, "invalid_operation")
        return self.executors[kind]

    def create_draft(self, operation_type, parameters, *, actor="local-admin"):
        executor = self._executor(operation_type)
        if not isinstance(parameters, dict):
            raise OperationError(422, "invalid_operation")
        try:
            parameters = json.loads(canonical_json(parameters))
            with self.memory.transaction():
                self.conn.execute(
                    "UPDATE operation_drafts SET status='expired',parameters_json='{}',baseline_json='{}',diff_json='[]',warnings_json='[]',token_hash='' WHERE status='draft' AND expires_at<=?",
                    (self.clock(),),
                )
                baseline, diff, warnings = executor.prepare(parameters)
                token = secrets.token_urlsafe(32)
                expires = self.clock() + 600
                row = self.conn.execute(
                    "INSERT INTO operation_drafts(operation_type,parameters_json,baseline_json,diff_json,warnings_json,token_hash,expires_at,status,actor,created_at) VALUES(?,?,?,?,?,?,?,'draft',?,?)",
                    (
                        operation_type,
                        canonical_json(parameters),
                        canonical_json(baseline),
                        canonical_json(diff),
                        canonical_json(warnings),
                        self._hash(token),
                        expires,
                        actor,
                        self.clock(),
                    ),
                )
                return OperationPreview(
                    row.lastrowid,
                    operation_type,
                    tuple(diff),
                    tuple(warnings),
                    expires,
                    token,
                )
        except (ValueError, TypeError, KeyError) as exc:
            if isinstance(exc, OperationError):
                raise
            raise OperationError(
                422, "invalid_operation", "参数无效，请检查字段和范围。"
            ) from None

    def _row(self, draft_id):
        if type(draft_id) is not int or draft_id <= 0:
            raise OperationError(422, "invalid_draft")
        row = self.conn.execute(
            "SELECT * FROM operation_drafts WHERE id=?", (draft_id,)
        ).fetchone()
        if row is None:
            raise OperationError(404, "draft_not_found")
        if row["expires_at"] <= self.clock() or row["status"] == "expired":
            raise OperationError(410, "expired_draft")
        if row["status"] != "draft":
            raise OperationError(409, "draft_not_pending")
        if row["baseline_json"] == "{}":
            raise OperationError(409, "stale_draft")
        return row

    def preview(self, draft_id):
        # Reopening rotates the token; the database never stores recoverable tokens.
        try:
            with self.memory.transaction():
                row = self._row(draft_id)
                token = secrets.token_urlsafe(32)
                self.conn.execute(
                    "UPDATE operation_drafts SET token_hash=? WHERE id=?",
                    (self._hash(token), draft_id),
                )
                return OperationPreview(
                    row["id"],
                    row["operation_type"],
                    tuple(json.loads(row["diff_json"])),
                    tuple(json.loads(row["warnings_json"])),
                    row["expires_at"],
                    token,
                )
        except OperationError as exc:
            if exc.code == "expired_draft":
                self._expire(draft_id)
            raise

    def _expire(self, draft_id):
        with self.memory.transaction():
            self.conn.execute(
                "UPDATE operation_drafts SET status='expired',parameters_json='{}',baseline_json='{}',diff_json='[]',warnings_json='[]',token_hash='' WHERE id=? AND status='draft'",
                (draft_id,),
            )

    def confirm(self, draft_id, confirmation_token):
        with self.memory._transaction_lock:
            return self._confirm_locked(draft_id, confirmation_token)

    def _confirm_locked(self, draft_id, confirmation_token):
        if (
            not isinstance(confirmation_token, str)
            or not 16 <= len(confirmation_token) <= 256
        ):
            raise OperationError(403, "invalid_confirmation_token")
        try:
            self.conn.execute("BEGIN IMMEDIATE")
            with self.memory.transaction():
                row = self._row(draft_id)
                if not secrets.compare_digest(
                    row["token_hash"], self._hash(confirmation_token)
                ):
                    raise OperationError(403, "invalid_confirmation_token")
                params = json.loads(row["parameters_json"])
                before = json.loads(row["baseline_json"])
                executor = self._executor(row["operation_type"])
                if canonical_json(executor.snapshot(params)) != canonical_json(before):
                    raise OperationError(409, "stale_draft")
                result = executor.execute(params)
                audit = self.conn.execute(
                    "INSERT INTO audit_events(draft_id,operation_type,actor,status,before_json,after_json,created_at) VALUES(?,?,?,'success',?,?,?)",
                    (
                        draft_id,
                        row["operation_type"],
                        row["actor"],
                        canonical_json(before),
                        canonical_json(result),
                        self.clock(),
                    ),
                )
                self.conn.execute(
                    "UPDATE operation_drafts SET status='confirmed',parameters_json='{}',baseline_json='{}',diff_json='[]',warnings_json='[]',token_hash='' WHERE id=?",
                    (draft_id,),
                )
            self.conn.commit()
            return {"audit_id": audit.lastrowid, "draft_id": draft_id, "result": result}
        except OperationError as exc:
            self.conn.rollback()
            if exc.code == "expired_draft":
                self._expire(draft_id)
            raise
        except Exception:
            self.conn.rollback()
            try:
                with self.memory.transaction():
                    row = self.conn.execute(
                        "SELECT * FROM operation_drafts WHERE id=?", (draft_id,)
                    ).fetchone()
                    if row:
                        self.conn.execute(
                            "UPDATE operation_drafts SET status='failed',parameters_json='{}',baseline_json='{}',diff_json='[]',warnings_json='[]',token_hash='' WHERE id=?",
                            (draft_id,),
                        )
                        try:
                            with self.memory.transaction():
                                self.conn.execute(
                                    "INSERT INTO audit_events(draft_id,operation_type,actor,status,before_json,after_json,created_at,error) VALUES(?,?,?,'failed','{}','{}',?,'execution_failed')",
                                    (
                                        draft_id,
                                        row["operation_type"],
                                        row["actor"],
                                        self.clock(),
                                    ),
                                )
                        except Exception:
                            pass
            except Exception:
                pass
            raise OperationError(
                500, "execution_failed", "执行失败，更改已回滚。"
            ) from None

    def create_reverse_draft(self, audit_id):
        row = self.conn.execute(
            "SELECT * FROM audit_events WHERE id=? AND status='success'", (audit_id,)
        ).fetchone()
        if not row:
            raise OperationError(404, "audit_not_found")
        executor = self._executor(row["operation_type"])
        if not hasattr(executor, "reverse"):
            raise OperationError(422, "not_reversible")
        params = executor.reverse(
            json.loads(row["before_json"]), json.loads(row["after_json"])
        )
        return self.create_draft(row["operation_type"], params)
