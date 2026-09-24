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
import sqlite3
import time
from collections import deque
from pathlib import Path
from typing import Any, Optional

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


class MemoryStore:
    """两级记忆存储：短期工作记忆 + 长期持久化记忆。"""

    def __init__(self, db_path: str = "./data/memory.db", short_term_limit: int = 20):
        self.db_path = db_path
        self.short_term_limit = short_term_limit
        self._short_term: deque[tuple[str, str]] = deque(maxlen=short_term_limit)

        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------------ 短期记忆
    def add_short_term(self, role: str, content: str) -> None:
        """记录当前会话的一轮对话（role: user / assistant）。"""
        self._short_term.append((role, content))

    def get_short_term(self) -> list[dict[str, str]]:
        """返回当前会话窗口（供 LLM 上下文使用）。"""
        return [{"role": r, "content": c} for r, c in self._short_term]

    def clear_short_term(self) -> None:
        """会话结束时清空短期窗口。"""
        self._short_term.clear()

    # ------------------------------------------------------------------ 长期记忆：通用片段
    def remember(
        self,
        content: str,
        memory_type: str = "fact",
        category: str = "general",
        importance: float = 0.5,
        tags: Optional[list[str]] = None,
        embedding: Optional[bytes] = None,
    ) -> int:
        """写入一条长期记忆片段，返回 id。"""
        cur = self._conn.execute(
            "INSERT INTO memory_fragments (content, memory_type, category, importance, "
            "last_accessed, created_at, content_vector) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (content, memory_type, category, importance, _now(), _now(), embedding),
        )
        fid = cur.lastrowid
        for tag in tags or []:
            self._conn.execute(
                "INSERT INTO memory_tags (fragment_id, tag) VALUES (?, ?)", (fid, tag)
            )
        self._conn.commit()
        return fid

    def recall(
        self,
        query: Optional[str] = None,
        memory_type: Optional[str] = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """检索长期记忆。

        - 有 query：按关键词匹配 + 命中数计分，返回最相关的
        - 无 query：按重要度 + 最近访问排序
        """
        tokens = _tokenize(query) if query else []
        if tokens:
            like = " OR ".join(["content LIKE ?"] * len(tokens))
            sql = "SELECT * FROM memory_fragments WHERE " + like
            params: list[Any] = [f"%{t}%" for t in tokens]
            if memory_type:
                sql += " AND memory_type = ?"
                params.append(memory_type)
            rows = self._conn.execute(sql, params).fetchall()
            # 命中关键词越多越相关；同分按重要度、最近访问排序
            scored = [(sum(1 for t in tokens if t in r["content"]), r) for r in rows]
            scored.sort(key=lambda x: (-x[0], -x[1]["importance"], -x[1]["last_accessed"]))
            return [dict(r) for _, r in scored[:limit]]

        sql = "SELECT * FROM memory_fragments"
        params = []
        if memory_type:
            sql += " WHERE memory_type = ?"
            params.append(memory_type)
        sql += " ORDER BY importance DESC, last_accessed DESC LIMIT ?"
        params.append(limit)
        return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def touch(self, fragment_id: int) -> None:
        """更新某条记忆的最近访问时间。"""
        self._conn.execute(
            "UPDATE memory_fragments SET last_accessed = ? WHERE id = ?",
            (_now(), fragment_id),
        )
        self._conn.commit()

    def forget(self, fragment_id: int) -> None:
        """删除一条记忆片段及其标签。"""
        self._conn.execute("DELETE FROM memory_fragments WHERE id = ?", (fragment_id,))
        self._conn.execute(
            "DELETE FROM memory_tags WHERE fragment_id = ?", (fragment_id,)
        )
        self._conn.commit()

    # ------------------------------------------------------------------ 长期记忆：专用类型
    def remember_user(self, key: str, value: str) -> int:
        """记录用户画像（身份记忆）。"""
        return self.remember(
            f"{key}: {value}",
            memory_type="user_profile",
            category="user",
            importance=0.9,
        )

    def get_user_profile(self) -> dict[str, str]:
        """读取用户画像为 key->value 字典。"""
        rows = self.recall(memory_type="user_profile", limit=100)
        profile: dict[str, str] = {}
        for r in rows:
            if ": " in r["content"]:
                k, v = r["content"].split(": ", 1)
                profile[k] = v
        return profile

    def add_episode(
        self, event_type: str, content: str, participants: Optional[list[str]] = None
    ) -> int:
        """记录一条事件记忆。"""
        cur = self._conn.execute(
            "INSERT INTO memory_episodic (event_type, content, participants, created_at) "
            "VALUES (?, ?, ?, ?)",
            (event_type, content, ",".join(participants) if participants else None, _now()),
        )
        self._conn.commit()
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
        self._conn.commit()
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
        self._conn.commit()
        return cur.lastrowid

    def list_ideas(self) -> list[dict[str, Any]]:
        return [
            dict(r)
            for r in self._conn.execute(
                "SELECT * FROM memory_short_term_ideas ORDER BY created_at DESC"
            ).fetchall()
        ]

    # ------------------------------------------------------------------ 向量接口（预留）
    def embed(self, text: str) -> Optional[bytes]:
        """embedding 钩子：默认不实现，返回 None。

        接入 embedding 模型后覆盖此方法（如返回 np.ndarray 的 bytes），
        即可配合 vector_search 做语义检索。
        """
        return None

    def vector_search(self, embedding: bytes, limit: int = 10) -> list[dict[str, Any]]:
        """向量检索（预留）：无 embedding 时退化为按重要度返回。"""
        return self.recall(limit=limit)

    def close(self) -> None:
        self._conn.close()
