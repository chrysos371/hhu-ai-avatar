"""Single-user management storage on the existing memory transaction boundary."""

import json
import time


def canonical_json(value):
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


class AdminStore:
    def __init__(self, memory):
        self.memory = memory
        self.conn = memory._conn

    def migrate(self, initial_persona):
        statements = [
            "CREATE TABLE IF NOT EXISTS admin_state (key TEXT PRIMARY KEY,value TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS persona_versions (id INTEGER PRIMARY KEY AUTOINCREMENT,parent_id INTEGER,data_json TEXT NOT NULL,created_at REAL NOT NULL)",
            "CREATE TABLE IF NOT EXISTS emotion_overrides (id INTEGER PRIMARY KEY AUTOINCREMENT,data_json TEXT NOT NULL,starts_at REAL NOT NULL,expires_at REAL NOT NULL,status TEXT NOT NULL CHECK(status IN ('active','replaced','cleared')))",
            "CREATE TABLE IF NOT EXISTS knowledge_sources (id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,sha256 TEXT NOT NULL UNIQUE,created_at REAL NOT NULL)",
            "CREATE TABLE IF NOT EXISTS knowledge_chunks (id INTEGER PRIMARY KEY AUTOINCREMENT,source_id INTEGER NOT NULL REFERENCES knowledge_sources(id),content TEXT NOT NULL,sha256 TEXT NOT NULL UNIQUE)",
            "CREATE TABLE IF NOT EXISTS operation_drafts (id INTEGER PRIMARY KEY AUTOINCREMENT,operation_type TEXT NOT NULL CHECK(operation_type IN ('persona.update','emotion.override','knowledge.import','memory.batch')),parameters_json TEXT NOT NULL,baseline_json TEXT NOT NULL,diff_json TEXT NOT NULL,warnings_json TEXT NOT NULL,token_hash TEXT NOT NULL,expires_at REAL NOT NULL,status TEXT NOT NULL CHECK(status IN ('draft','confirmed','expired','failed')),actor TEXT NOT NULL,created_at REAL NOT NULL)",
            "CREATE TABLE IF NOT EXISTS audit_events (id INTEGER PRIMARY KEY AUTOINCREMENT,draft_id INTEGER,operation_type TEXT NOT NULL,actor TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN ('success','failed')),before_json TEXT NOT NULL,after_json TEXT NOT NULL,created_at REAL NOT NULL,error TEXT)",
        ]
        with self.memory.transaction():
            for sql in statements:
                self.conn.execute(sql)
            columns = {
                r["name"]
                for r in self.conn.execute("PRAGMA table_info(knowledge_chunks)")
            }
            for name, kind in [("content_vector", "BLOB"), ("embedding_model", "TEXT")]:
                if name not in columns:
                    self.conn.execute(
                        f"ALTER TABLE knowledge_chunks ADD COLUMN {name} {kind}"
                    )
            self.conn.execute(
                "UPDATE operation_drafts SET status='expired',parameters_json='{}',baseline_json='{}',diff_json='[]',warnings_json='[]',token_hash='' WHERE status='draft' AND expires_at<=?",
                (time.time(),),
            )
            if not self.conn.execute(
                "SELECT value FROM admin_state WHERE key='persona'"
            ).fetchone():
                row = self.conn.execute(
                    "INSERT INTO persona_versions(parent_id,data_json,created_at) VALUES(NULL,?,?)",
                    (canonical_json(initial_persona), time.time()),
                )
                self.conn.execute(
                    "INSERT INTO admin_state(key,value) VALUES('persona',?)",
                    (str(row.lastrowid),),
                )

    def current_persona(self):
        row = self.conn.execute(
            "SELECT p.* FROM persona_versions p JOIN admin_state s ON s.key='persona' AND p.id=CAST(s.value AS INTEGER)"
        ).fetchone()
        return self.persona_row(row) if row else None

    @staticmethod
    def persona_row(row):
        return {
            "id": row["id"],
            "parent_id": row["parent_id"],
            "data": json.loads(row["data_json"]),
            "created_at": row["created_at"],
        }

    def list_audit(
        self, *, limit=100, before_id=None, operation_type=None, status=None
    ):
        if (
            type(limit) is not int
            or not 1 <= limit <= 200
            or (
                before_id is not None and (type(before_id) is not int or before_id <= 0)
            )
        ):
            raise ValueError("invalid pagination")
        if operation_type is not None and operation_type not in (
            "persona.update",
            "emotion.override",
            "knowledge.import",
            "memory.batch",
        ):
            raise ValueError("invalid operation filter")
        if status is not None and status not in ("success", "failed"):
            raise ValueError("invalid audit status")
        rows = self.conn.execute(
            "SELECT * FROM audit_events WHERE (? IS NULL OR id<?) AND (? IS NULL OR operation_type=?) AND (? IS NULL OR status=?) ORDER BY id DESC LIMIT ?",
            (
                before_id,
                before_id,
                operation_type,
                operation_type,
                status,
                status,
                limit,
            ),
        ).fetchall()
        return [
            dict(
                id=r["id"],
                draft_id=r["draft_id"],
                operation_type=r["operation_type"],
                actor=r["actor"],
                status=r["status"],
                before=json.loads(r["before_json"]),
                after=json.loads(r["after_json"]),
                created_at=r["created_at"],
                error=r["error"],
            )
            for r in rows
        ]

    def system_counts(self):
        return {
            name: self.conn.execute(sql).fetchone()[0]
            for name, sql in {
                "memories": "SELECT COUNT(*) FROM memory_fragments WHERE status='active'",
                "knowledge_sources": "SELECT COUNT(*) FROM knowledge_sources",
                "knowledge_chunks": "SELECT COUNT(*) FROM knowledge_chunks",
                "audit_events": "SELECT COUNT(*) FROM audit_events",
            }.items()
        }


def initial_persona():
    from ..config import config

    return dict(
        name=config.avatar_name,
        core_identity=config.avatar_persona,
        expression_principles="自然、清晰，先完成用户任务",
        relationship_boundaries="支持现实关系，不鼓励排他依赖",
        immutable_rules="事实须有来源；不得编造身体或共同经历；危险情绪优先现实安全",
        temperature_bias=0.0,
        initiative=0.5,
    )
