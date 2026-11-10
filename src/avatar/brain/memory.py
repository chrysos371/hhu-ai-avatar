"""记忆系统：翻译自 AIRI 的记忆 schema，用 SQLite 实现两级记忆。

参考 AIRI（moeru-ai/airi）的表结构（integrations/telegram-bot/drizzle/*.sql）：
- memory_fragments      通用记忆片段（含重要度、向量位）
- memory_episodic       事件记忆
- memory_long_term_goals 长期目标
- memory_short_term_ideas 短期想法（excitement 即情绪强度）
- memory_tags           片段标签

两级记忆：
- 短期工作记忆：内存 deque，存当前会话最近 N 轮
- 长期记忆：SQLite 持久化，按重要度与访问时间管理
"""
from __future__ import annotations

import re
import logging
import sqlite3
import time
from collections import deque
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Optional

import numpy as np

from .embeddings import normalized_vector
from .preferences import canonical_preference_object

logger = logging.getLogger(__name__)

# 建表 SQL（翻译自 AIRI schema）
_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_fragments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    content       TEXT    NOT NULL,
    memory_type   TEXT    NOT NULL DEFAULT 'fact',   -- fact/episode/user_profile/preference/goal
    category      TEXT    NOT NULL DEFAULT 'general',
    importance    REAL    NOT NULL DEFAULT 0.5,       -- 0~1
    last_accessed REAL    NOT NULL DEFAULT 0,
    created_at    REAL    NOT NULL DEFAULT 0,
    content_vector BLOB                                -- 预留：embedding 向量
);
CREATE INDEX IF NOT EXISTS idx_fragments_type       ON memory_fragments(memory_type);
CREATE INDEX IF NOT EXISTS idx_fragments_importance ON memory_fragments(importance);

CREATE TABLE IF NOT EXISTS memory_episodic (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type   TEXT    NOT NULL,
    content      TEXT    NOT NULL,
    participants TEXT,
    created_at   REAL    NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS memory_long_term_goals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    description TEXT,
    priority    INTEGER NOT NULL DEFAULT 3,           -- 1~5
    progress    REAL    NOT NULL DEFAULT 0,           -- 0~1
    deadline    TEXT,
    status      TEXT    NOT NULL DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS memory_short_term_ideas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    content     TEXT    NOT NULL,
    source_type TEXT    NOT NULL DEFAULT 'chat',
    status      TEXT    NOT NULL DEFAULT 'open',
    excitement  INTEGER NOT NULL DEFAULT 5,           -- 1~10 情绪强度
    created_at  REAL    NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS memory_tags (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    fragment_id INTEGER NOT NULL,
    tag         TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tags_tag ON memory_tags(tag);
CREATE TABLE IF NOT EXISTS memory_context_revision (
    id INTEGER PRIMARY KEY CHECK (id=1), revision INTEGER NOT NULL
);
INSERT OR IGNORE INTO memory_context_revision(id,revision) VALUES (1,0);
-- Summary stores references only: never another copy of private source text.
CREATE TABLE IF NOT EXISTS memory_summary_items (
    session_id TEXT NOT NULL,
    source_message_id INTEGER NOT NULL,
    PRIMARY KEY (session_id, source_message_id)
);

CREATE TABLE IF NOT EXISTS memory_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    session_id TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS memory_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fragment_id INTEGER NOT NULL,
    source_message_id INTEGER,
    evidence TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sources_fragment ON memory_sources(fragment_id);
CREATE INDEX IF NOT EXISTS idx_sources_message ON memory_sources(source_message_id);
-- Corrections can merge two previously independent version chains. Keep the
-- extra link instead of rewriting either chain's historical predecessor.
CREATE TABLE IF NOT EXISTS memory_version_links (
    fragment_id INTEGER NOT NULL,
    related_fragment_id INTEGER NOT NULL,
    PRIMARY KEY (fragment_id, related_fragment_id)
);
"""


def _now() -> float:
    return time.time()


# 检索停用词：切分 query 时过滤掉，只保留有区分度的实词
_STOPWORDS = {
    "的", "了", "吗", "呢", "吧", "啊", "呀", "哦", "嗯", "嘛",
    "我", "你", "他", "她", "它", "您", "咱",
    "是", "在", "有", "和", "与", "就", "都", "很", "也", "还", "又", "再",
    "要", "会", "能", "可", "想",
    "这", "那", "个", "些", "们",
    "我们", "你们", "他们", "她们", "它们", "自己", "大家",
    "什么", "怎么", "为什么", "谁", "哪里", "哪儿", "多少", "如何",
    "这个", "那个", "这些", "那些", "一个", "一下",
    "今天", "明天", "昨天", "现在", "刚才", "已经", "正在",
    "觉得", "感觉", "知道", "记得", "记住", "忘记",
    "叫", "喜欢", "讨厌", "希望", "想", "要",
}


def _tokenize(text: str) -> list[str]:
    """把 query 切成有区分度的关键词（简单中文切分：按停用词/标点分隔）。"""
    text = re.sub(r"[^一-鿿A-Za-z0-9]", " ", text)
    for sw in sorted(_STOPWORDS, key=len, reverse=True):
        text = text.replace(sw, " ")
    return [seg for seg in text.split() if seg]


def _profile_metadata(content: str, memory_type: str) -> tuple[Optional[str], Optional[str], Optional[int]]:
    """仅规范明确的偏好前缀；不同活动和未知对象保持原文，不做语义猜测。"""
    key = None
    value = content.strip()
    if memory_type == 'user_profile' and ': ' in content:
        key, value = content.split(': ', 1)
        key, value = key.strip(), value.strip()
    if key not in ('偏好', '爱好') and memory_type != 'preference':
        return key, None, None
    match = re.fullmatch(r'(?:我)?(不再喜欢|不喜欢|不爱|讨厌|喜欢|喜爱|爱好|爱)(.+)', value)
    polarity = 1
    if match:
        prefix, value = match.groups()
        polarity = -1 if prefix in ('不再喜欢', '不喜欢', '不爱', '讨厌') else 1
    value = canonical_preference_object(value)
    return key, value or None, polarity


class MemoryStore:
    """两级记忆存储：短期工作记忆 + 长期持久化记忆。"""

    def __init__(self, db_path: str = "./data/memory.db", short_term_limit: int = 20,
                 embedder=None, semantic_threshold: float = 0.45):
        if not 0 <= semantic_threshold <= 1:
            raise ValueError('semantic threshold must be within 0..1')
        self.db_path = db_path
        self.short_term_limit = short_term_limit
        self._short_term: deque[tuple[str, str]] = deque(maxlen=short_term_limit)

        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._transaction_depth = 0
        self._embedder = embedder
        self.semantic_threshold = semantic_threshold
        self._migrate()
        self._seen_context_revision = self.context_revision

    def _migrate(self) -> None:
        """Add columns without replacing legacy rows; normalize each old row once."""
        additions = {
            'status': "TEXT NOT NULL DEFAULT 'active'",
            'valid_from': 'REAL', 'valid_to': 'REAL', 'predecessor_id': 'INTEGER',
            'profile_key': 'TEXT', 'preference_object': 'TEXT', 'preference_polarity': 'INTEGER',
            'embedding_model': 'TEXT', 'embedding_dim': 'INTEGER',
            'bad_hits': 'INTEGER NOT NULL DEFAULT 0',
        }
        with self.transaction():
            columns = {row['name'] for row in self._conn.execute('PRAGMA table_info(memory_fragments)')}
            for name, declaration in additions.items():
                if name not in columns:
                    self._conn.execute(f'ALTER TABLE memory_fragments ADD COLUMN {name} {declaration}')
            legacy = self._conn.execute(
                'SELECT * FROM memory_fragments WHERE valid_from IS NULL ORDER BY created_at, id'
            ).fetchall()
            for row in legacy:
                key, obj, polarity = _profile_metadata(row['content'], row['memory_type'])
                self._conn.execute(
                    'UPDATE memory_fragments SET valid_from=?, profile_key=?, '
                    'preference_object=?, preference_polarity=? WHERE id=?',
                    (row['created_at'], key, obj, polarity, row['id']),
                )
                # Only already-normalized earlier rows can be predecessors.
                previous = self._current_match(row['content'], row['memory_type'],
                                               row['category'], key, obj,
                                               exclude_id=row['id'])
                if previous is not None:
                    self._supersede(previous['id'], row['id'], row['created_at'])
            self._conn.execute('CREATE INDEX IF NOT EXISTS idx_fragments_current '
                               'ON memory_fragments(status, memory_type)')

    def _current_match(self, content, memory_type, category, key, obj, *, exclude_id=None):
        sql = "SELECT * FROM memory_fragments WHERE status='active' AND valid_from IS NOT NULL"
        params: list[Any] = []
        if key:
            sql += ' AND memory_type=?'
            params.append(memory_type)
            if key in ('偏好', '爱好'):
                sql += " AND profile_key IN ('偏好', '爱好') AND preference_object IS ?"
                params.append(obj)
            else:
                sql += ' AND profile_key=?'
                params.append(key)
        elif memory_type == 'preference' and obj:
            sql += ' AND memory_type=? AND preference_object=?'
            params.extend([memory_type, obj])
        else:
            sql += ' AND memory_type=? AND category=? AND content=?'
            params.extend([memory_type, category, content])
        if exclude_id is not None:
            sql += ' AND id != ?'
            params.append(exclude_id)
        sql += ' ORDER BY created_at DESC, id DESC LIMIT 1'
        return self._conn.execute(sql, params).fetchone()

    def _supersede(self, previous_id: int, current_id: int, timestamp: float) -> None:
        self._conn.execute("UPDATE memory_fragments SET status='superseded', valid_to=? WHERE id=?",
                           (timestamp, previous_id))
        self._conn.execute('UPDATE memory_fragments SET predecessor_id=? WHERE id=?',
                           (previous_id, current_id))

    @contextmanager
    def transaction(self):
        """Acquire write intent before reads; nested batches retain savepoint rollback."""
        owned = self._transaction_depth == 0 and not self._conn.in_transaction
        if owned:
            self._conn.execute('BEGIN IMMEDIATE')
        context = None
        seen_revision = getattr(self, '_seen_context_revision', None)
        savepoint = f"memory_batch_{self._transaction_depth}"
        try:
            if seen_revision is not None:
                self._refresh_context()
                seen_revision = self._seen_context_revision
            context = list(self._short_term)
            self._conn.execute(f"SAVEPOINT {savepoint}")
            self._transaction_depth += 1
            try:
                yield
            except BaseException:
                self._conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
                self._short_term.clear()
                self._short_term.extend(context)
                self._seen_context_revision = seen_revision if seen_revision is not None else self.context_revision
                raise
            finally:
                self._transaction_depth -= 1
                self._conn.execute(f"RELEASE SAVEPOINT {savepoint}")
            if owned:
                self._conn.commit()
        except BaseException:
            if owned:
                self._conn.rollback()
                if context is not None:
                    self._short_term.clear()
                    self._short_term.extend(context)
                    self._seen_context_revision = seen_revision if seen_revision is not None else self.context_revision
            raise

    def _commit(self) -> None:
        if not self._transaction_depth:
            self._conn.commit()

    # ------------------------------------------------------------------ 短期记忆
    def add_short_term(self, role: str, content: str) -> None:
        """记录当前会话的一轮对话（role: user / assistant）。"""
        self._refresh_context()
        self._short_term.append((role, content))

    def get_short_term(self) -> list[dict[str, str]]:
        """返回当前会话窗口（供 LLM 上下文使用）。"""
        self._refresh_context()
        return [{"role": r, "content": c} for r, c in self._short_term]

    @property
    def context_revision(self) -> int:
        return self._conn.execute('SELECT revision FROM memory_context_revision WHERE id=1').fetchone()[0]

    def _refresh_context(self) -> None:
        revision = self.context_revision
        if revision != self._seen_context_revision:
            self._short_term.clear()
            self._seen_context_revision = revision

    def _invalidate_context(self) -> None:
        self._conn.execute('UPDATE memory_context_revision SET revision=revision+1 WHERE id=1')
        self._conn.execute('DELETE FROM memory_summary_items')
        if self._conn.execute("SELECT 1 FROM sqlite_master WHERE name='operation_drafts' AND type='table'").fetchone():
            self._conn.execute("UPDATE operation_drafts SET parameters_json='{}',baseline_json='{}',diff_json='[]',warnings_json='[]',token_hash='' WHERE operation_type='memory.batch'")
        self.clear_short_term()
        self._seen_context_revision = self.context_revision

    def clear_short_term(self) -> None:
        """会话结束时清空短期窗口。"""
        self._short_term.clear()

    def add_message(self, role: str, content: str, session_id: str) -> int:
        """Persist a conversation message independently of the context window."""
        if role not in ('user', 'assistant', 'system'):
            raise ValueError('unsupported message role')
        cur = self._conn.execute(
            'INSERT INTO memory_messages (role, content, session_id, created_at) VALUES (?, ?, ?, ?)',
            (role, content, session_id, _now()),
        )
        self._commit()
        return cur.lastrowid

    def _add_source(self, fragment_id: int, source_message_id: Optional[int], evidence: Optional[str]) -> None:
        if source_message_id is None and evidence is None:
            return
        if source_message_id is not None and not self._conn.execute(
            'SELECT 1 FROM memory_messages WHERE id=?', (source_message_id,)
        ).fetchone():
            raise ValueError('source message does not exist')
        self._conn.execute(
            'INSERT INTO memory_sources (fragment_id, source_message_id, evidence, created_at) VALUES (?, ?, ?, ?)',
            (fragment_id, source_message_id, evidence, _now()),
        )

    # ------------------------------------------------------------------ 长期记忆：通用片段
    def remember(
        self,
        content: str,
        memory_type: str = "fact",
        category: str = "general",
        importance: float = 0.5,
        tags: Optional[list[str]] = None,
        embedding: Optional[bytes] = None,
        *,
        source_message_id: Optional[int] = None,
        evidence: Optional[str] = None,
    ) -> int:
        """写入一条长期记忆片段，返回 id。"""
        with self.transaction():
            key, obj, polarity = _profile_metadata(content, memory_type)
            previous = self._current_match(content, memory_type, category, key, obj)
            same = previous is not None and (
                previous['content'] == content or
                (obj is not None and previous['preference_polarity'] == polarity)
            )
            if same:
                fid = previous['id']
            else:
                now = _now()
                cur = self._conn.execute(
                    'INSERT INTO memory_fragments (content, memory_type, category, importance, '
                    'last_accessed, created_at, content_vector, valid_from, profile_key, '
                    'preference_object, preference_polarity) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    (content, memory_type, category, importance, now, now, embedding, now, key, obj, polarity),
                )
                fid = cur.lastrowid
                if previous is not None:
                    self._supersede(previous['id'], fid, now)
            self._add_source(fid, source_message_id, evidence)
            for tag in tags or []:
                self._conn.execute(
                    'INSERT INTO memory_tags (fragment_id, tag) SELECT ?, ? WHERE NOT EXISTS '
                    '(SELECT 1 FROM memory_tags WHERE fragment_id=? AND tag=?)',
                    (fid, tag, fid, tag),
                )
            return fid

    def recall(
        self, query: Optional[str] = None, memory_type: Optional[str] = None,
        limit: int = 10, *, include_history: bool = False,
    ) -> list[dict[str, Any]]:
        """Hybrid recall of current facts; failures preserve deterministic lexical behavior."""
        if limit <= 0:
            return []
        lexical = self._lexical_recall(query, memory_type, max(limit * 2, 20),
                                       include_history=include_history)
        if not query or include_history or self._embedder is None:
            return lexical[:limit]
        try:
            vector = self.embed(query)
            semantic = self.vector_search(vector, limit=max(limit * 2, 20), memory_type=memory_type)
        except Exception:
            logger.warning('语义召回不可用，使用关键词检索')
            return lexical[:limit]
        rows = {row['id']: row for row in lexical + semantic}
        scores = {}
        for results in (lexical, semantic):
            for rank, row in enumerate(results, 1):
                scores[row['id']] = scores.get(row['id'], 0.) + 1. / (60 + rank)
        ranked = sorted(rows.values(), key=lambda row: (
            scores[row['id']] * self._recall_weight(row), row.get('similarity', 0.), row['importance'], row['id']), reverse=True)
        return ranked[:limit]

    def _lexical_recall(
        self,
        query: Optional[str] = None,
        memory_type: Optional[str] = None,
        limit: int = 10,
        *,
        include_history: bool = False,
    ) -> list[dict[str, Any]]:
        """检索长期记忆。

        - 有 query：按关键词匹配 + 命中数计分，返回最相关的
        - 无 query：按重要度 + 最近访问排序
        """
        tokens = _tokenize(query) if query else []
        # An explicitly supplied query with no searchable terms is not a request
        # to browse the memory library; reserve importance-ranked listing for
        # None or an empty query only.
        if query and query.strip() and not tokens:
            return []
        if tokens:
            like = " OR ".join(["content LIKE ?"] * len(tokens))
            sql = "SELECT * FROM memory_fragments WHERE (" + like + ")"
            params: list[Any] = [f"%{t}%" for t in tokens]
            if memory_type:
                sql += " AND memory_type = ?"
                params.append(memory_type)
            if not include_history:
                sql += " AND status = 'active'"
            rows = self._conn.execute(sql, params).fetchall()
            # 命中关键词越多越相关；同分按重要度、最近访问排序
            scored = [(sum(1 for t in tokens if t in r["content"]), r) for r in rows]
            scored.sort(key=lambda x: (-x[0] * self._recall_weight(dict(x[1])), -x[1]["last_accessed"]))
            return [dict(r) for _, r in scored[:limit]]

        sql = "SELECT * FROM memory_fragments WHERE 1=1"
        params = []
        if memory_type:
            sql += " AND memory_type = ?"
            params.append(memory_type)
        if not include_history:
            sql += " AND status = 'active'"
        sql += " ORDER BY importance DESC, last_accessed DESC LIMIT ?"
        params.append(limit)
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def memory_strength(self, row: dict, now: Optional[float] = None) -> float:
        """Time affects ranking only; identity, explicit rules and preferences remain stable."""
        if row['memory_type'] in ('user_profile', 'preference', 'rule'):
            return 1.0
        days = max(0, (_now() if now is None else now) - row['created_at']) / 86400
        return 2 ** (-min(days / 30, 1000))

    def _recall_weight(self, row: dict) -> float:
        return ((.25 + .75 * self.memory_strength(row)) * (.4 + .6 * row['importance'])
                / (1 + row.get('bad_hits', 0)))

    def report_irrelevant(self, fragment_id: int) -> None:
        """Explicit retrieval feedback, never an automatic factual correction or deletion."""
        cur = self._conn.execute(
            "UPDATE memory_fragments SET bad_hits=bad_hits+1 WHERE id=? AND status='active'",
            (fragment_id,))
        if not cur.rowcount:
            raise ValueError('active memory does not exist')
        self._commit()

    def touch(self, fragment_id: int) -> None:
        """更新某条记忆的最近访问时间。"""
        self._conn.execute(
            "UPDATE memory_fragments SET last_accessed = ? WHERE id = ?",
            (_now(), fragment_id),
        )
        self._commit()

    def forget(self, fragment_id: int) -> None:
        """Hard-delete a whole version chain and redact shared private evidence."""
        with self.transaction():
            ids = self._version_ids(fragment_id)
            if not ids:
                return
            marks = ','.join('?' for _ in ids)
            messages = self._conn.execute(
                f'SELECT DISTINCT source_message_id FROM memory_sources WHERE fragment_id IN ({marks}) '
                'AND source_message_id IS NOT NULL', ids,
            ).fetchall()
            for message in messages:
                mid = message['source_message_id']
                self._conn.execute("UPDATE memory_messages SET content='[redacted]' WHERE id=?", (mid,))
                # Another fact may quote the entire same original message as its
                # evidence. Keep that fact and association, but remove the quote.
                self._conn.execute("UPDATE memory_sources SET evidence='[redacted]' WHERE source_message_id=?", (mid,))
            for table, column in (('memory_tags', 'fragment_id'), ('memory_sources', 'fragment_id'),
                                  ('memory_version_links', 'fragment_id'),
                                  ('memory_version_links', 'related_fragment_id'),
                                  ('memory_fragments', 'id')):
                self._conn.execute(f'DELETE FROM {table} WHERE {column} IN ({marks})', ids)
            self._invalidate_context()

    def _version_ids(self, fragment_id: int) -> list[int]:
        """All connected predecessors, successors and correction merge links."""
        rows = self._conn.execute(
            'WITH RECURSIVE versions(id) AS ('
            'SELECT id FROM memory_fragments WHERE id=? UNION '
            'SELECT f.id FROM memory_fragments f JOIN versions v ON f.predecessor_id=v.id UNION '
            'SELECT f.predecessor_id FROM memory_fragments f JOIN versions v '
            'ON f.id=v.id WHERE f.predecessor_id IS NOT NULL UNION '
            'SELECT l.related_fragment_id FROM memory_version_links l JOIN versions v ON l.fragment_id=v.id UNION '
            'SELECT l.fragment_id FROM memory_version_links l JOIN versions v ON l.related_fragment_id=v.id'
            ') SELECT id FROM versions', (fragment_id,),
        ).fetchall()
        return [row['id'] for row in rows]

    def inspect(self, fragment_id: int) -> Optional[dict[str, Any]]:
        """Return one fact, including history and its durable source messages."""
        row = self._conn.execute('SELECT * FROM memory_fragments WHERE id=?', (fragment_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result['tags'] = [r['tag'] for r in self._conn.execute(
            'SELECT tag FROM memory_tags WHERE fragment_id=? ORDER BY id', (fragment_id,))]
        result['sources'] = [dict(r) for r in self._conn.execute(
            'SELECT s.*, m.role, m.content AS message_content, m.session_id, '
            'm.created_at AS message_created_at FROM memory_sources s '
            'LEFT JOIN memory_messages m ON m.id=s.source_message_id '
            'WHERE s.fragment_id=? ORDER BY s.id', (fragment_id,))]
        return result

    def list_memories(self, include_history: bool = False, limit: int = 100) -> list[dict[str, Any]]:
        return self.recall(limit=limit, include_history=include_history)

    def correct(self, fragment_id: int, content: str, *, evidence: str = 'manual correction') -> int:
        """Create a manual version; never mutate the old fact or its evidence."""
        if not isinstance(content, str) or not content.strip():
            raise ValueError('correction content must be non-empty')
        with self.transaction():
            old = self.inspect(fragment_id)
            if old is None:
                raise ValueError('memory does not exist')
            content = content.strip()
            if old['profile_key']:
                prefix = old['profile_key'] + ': '
                if content.startswith(old['profile_key'] + ':'):
                    content = prefix + content.split(':', 1)[1].strip()
                else:
                    content = prefix + content
                if not content[len(prefix):].strip():
                    raise ValueError('profile value must be non-empty')
            key, obj, polarity = _profile_metadata(content, old['memory_type'])
            now = _now()
            cur = self._conn.execute(
                'INSERT INTO memory_fragments (content,memory_type,category,importance,last_accessed,'
                'created_at,valid_from,profile_key,preference_object,preference_polarity) '
                'VALUES (?,?,?,?,?,?,?,?,?,?)',
                (content, old['memory_type'], old['category'], old['importance'], now, now, now, key, obj, polarity),
            )
            fid = cur.lastrowid
            # A correction from an older version still replaces the latest
            # current fact in that chain, plus any colliding current identity.
            ids = self._version_ids(fragment_id)
            marks = ','.join('?' for _ in ids)
            chain_current = self._conn.execute(
                f"SELECT id FROM memory_fragments WHERE id IN ({marks}) AND status='active' "
                'ORDER BY created_at DESC, id DESC LIMIT 1', ids,
            ).fetchone()
            self._supersede(chain_current['id'] if chain_current else fragment_id, fid, now)
            collision = self._current_match(content, old['memory_type'], old['category'], key, obj, exclude_id=fid)
            if collision is not None:
                self._conn.execute("UPDATE memory_fragments SET status='superseded', valid_to=? WHERE id=?",
                                   (now, collision['id']))
                self._conn.execute('INSERT INTO memory_version_links (fragment_id,related_fragment_id) VALUES (?,?)',
                                   (fid, collision['id']))
            for tag in old['tags']:
                self._conn.execute('INSERT INTO memory_tags (fragment_id,tag) VALUES (?,?)', (fid, tag))
            self._add_source(fid, None, evidence)
            self._invalidate_context()
            return fid

    # ------------------------------------------------------------------ 长期记忆：专用类型
    def remember_user(self, key: str, value: str, *, source_message_id: Optional[int] = None,
                      evidence: Optional[str] = None) -> int:
        """记录用户画像（身份记忆）。"""
        content = f"{key}: {value}"
        return self.remember(
            content, memory_type="user_profile", category="user", importance=0.9,
            source_message_id=source_message_id, evidence=evidence,
        )

    def get_user_profile(self, *, include_history: bool = False) -> dict[str, str]:
        """按写入顺序读取画像；单值属性取最新，多值偏好保留不同项目。"""
        rows = self._conn.execute(
            "SELECT content FROM memory_fragments WHERE memory_type = ? "
            + ("" if include_history else "AND status = 'active' ")
            + "ORDER BY created_at DESC, id DESC", ("user_profile",)
        ).fetchall()
        values: dict[str, list[str]] = {}
        for r in rows:
            if ": " not in r["content"]:
                continue
            key, value = r["content"].split(": ", 1)
            bucket = values.setdefault(key, [])
            if value not in bucket and (not bucket or key in ("偏好", "爱好")):
                bucket.append(value)
        return {key: "；".join(items) for key, items in values.items()}

    def add_episode(
        self, event_type: str, content: str, participants: Optional[list[str]] = None
    ) -> int:
        """记录一条事件记忆。"""
        cur = self._conn.execute(
            "INSERT INTO memory_episodic (event_type, content, participants, created_at) "
            "VALUES (?, ?, ?, ?)",
            (event_type, content, ",".join(participants) if participants else None, _now()),
        )
        self._commit()
        return cur.lastrowid

    def list_episodes(
        self, event_type: Optional[str] = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM memory_episodic"
        params: list[Any] = []
        if event_type:
            sql += " WHERE event_type = ?"
            params.append(event_type)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def add_goal(
        self,
        title: str,
        description: Optional[str] = None,
        priority: int = 3,
        deadline: Optional[str] = None,
    ) -> int:
        """记录一个长期目标。"""
        cur = self._conn.execute(
            "INSERT INTO memory_long_term_goals (title, description, priority, deadline) "
            "VALUES (?, ?, ?, ?)",
            (title, description, priority, deadline),
        )
        self._commit()
        return cur.lastrowid

    def list_goals(self) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in self._conn.execute(
                "SELECT * FROM memory_long_term_goals ORDER BY priority DESC"
            ).fetchall()
        ]

    def add_idea(self, content: str, source_type: str = "chat", excitement: int = 5) -> int:
        """记录一条短期想法（excitement 1~10 表示情绪强度）。"""
        cur = self._conn.execute(
            "INSERT INTO memory_short_term_ideas (content, source_type, excitement, created_at) "
            "VALUES (?, ?, ?, ?)",
            (content, source_type, excitement, _now()),
        )
        self._commit()
        return cur.lastrowid

    def list_ideas(self) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in self._conn.execute(
                "SELECT * FROM memory_short_term_ideas ORDER BY created_at DESC"
            ).fetchall()
        ]

    # ------------------------------------------------------------------ 可选向量检索
    def embed(self, text: str) -> Optional[bytes]:
        if self._embedder is None:
            return None
        return normalized_vector(self._embedder.embed(text)).astype('<f4').tobytes()

    def _indexed_vectors(self, rows, dimensions=None, force=False):
        model = self._embedder.model_id
        if not isinstance(model, str) or not model:
            raise ValueError('Embedding provider must identify its vector space')
        results = []
        with self.transaction():
            for row in rows:
                vector = None
                if not force and row['embedding_model'] == model and row['content_vector'] is not None:
                    try:
                        cached = normalized_vector(np.frombuffer(row['content_vector'], dtype='<f4'))
                        if len(cached) == row['embedding_dim'] and (dimensions is None or len(cached) == dimensions):
                            vector = cached
                    except (ValueError, TypeError):
                        pass
                if vector is None:
                    vector = normalized_vector(self._embedder.embed(row['content']))
                    if dimensions is not None and len(vector) != dimensions:
                        raise ValueError('Embedding dimensions changed within one batch')
                    self._conn.execute('UPDATE memory_fragments SET content_vector=?, '
                                       'embedding_model=?,embedding_dim=? WHERE id=?',
                                       (vector.astype('<f4').tobytes(), model, len(vector), row['id']))
                if dimensions is None:
                    dimensions = len(vector)
                results.append((row, vector))
        return results

    def reindex(self) -> int:
        """Explicit atomic rebuild, e.g. after updating model weights under the same tag."""
        if self._embedder is None:
            return 0
        rows = self._conn.execute("SELECT * FROM memory_fragments WHERE status='active'").fetchall()
        self._indexed_vectors(rows, force=True)
        return len(rows)

    def vector_search(self, embedding: bytes, limit: int = 10, *,
                      memory_type: Optional[str] = None) -> list[dict[str, Any]]:
        if self._embedder is None:
            return self._lexical_recall(memory_type=memory_type, limit=limit)
        if embedding is None or limit <= 0:
            return []
        query = normalized_vector(np.frombuffer(embedding, dtype='<f4'))
        sql = "SELECT * FROM memory_fragments WHERE status='active'"
        params = []
        if memory_type:
            sql += ' AND memory_type=?'
            params.append(memory_type)
        rows = self._conn.execute(sql, params).fetchall()
        ranked = []
        for row, vector in self._indexed_vectors(rows, len(query)):
            score = float(np.dot(query, vector))
            if score >= self.semantic_threshold:
                result = dict(row, similarity=score, content_vector=vector.astype('<f4').tobytes(),
                              embedding_model=self._embedder.model_id, embedding_dim=len(vector))
                ranked.append(result)
        ranked.sort(key=lambda row: (row['similarity'], row['importance'], row['id']), reverse=True)
        if ranked:
            ranked = [row for row in ranked if row['similarity'] >= ranked[0]['similarity'] - 0.12]
        return ranked[:limit]

    def close(self) -> None:
        self._conn.close()
