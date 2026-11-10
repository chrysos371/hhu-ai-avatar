"""Previewed UTF-8 knowledge ingestion, isolated from personal memory."""

import hashlib
import re
import time
import numpy as np
from pathlib import PurePosixPath

MAX_BYTES = 5 * 1024 * 1024


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class KnowledgeService:
    def __init__(self, store):
        self.s = store
        self._vectors = {}

    def snapshot(self, p):
        return {
            "sources": [
                dict(r)
                for r in self.s.conn.execute(
                    "SELECT id,sha256 FROM knowledge_sources ORDER BY id"
                )
            ]
        }

    def preview_text(self, title, text):
        if (
            not isinstance(title, str)
            or not 1 <= len(title.strip()) <= 200
            or not isinstance(text, str)
            or not text.strip()
            or "\x00" in text
            or len(text.encode("utf-8")) > MAX_BYTES
        ):
            raise ValueError("invalid knowledge text")
        normalized = text.replace("\r\n", "\n")
        existing = {
            r[0] for r in self.s.conn.execute("SELECT sha256 FROM knowledge_chunks")
        }
        accepted = []
        rejected = []
        seen = set(existing)
        recent_grams = []
        provider = self.s.memory._embedder
        semantic = provider is not None
        self._vectors = {}
        previous_vectors = []
        semantic_status = "unconfigured" if not semantic else "available"
        if semantic:
            for row in self.s.conn.execute(
                "SELECT content_vector FROM knowledge_chunks WHERE embedding_model=? AND content_vector IS NOT NULL LIMIT 5000",
                (provider.model_id,),
            ):
                previous_vectors.append(np.frombuffer(row[0], dtype="<f4"))
        for paragraph in re.split(r"\n\s*\n", normalized):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            for offset in range(0, len(paragraph), 1000):
                chunk = paragraph[offset : offset + 1000]
                sha = digest(re.sub(r"\s+", " ", chunk).strip())
                grams = lambda t: set(t[i : i + 2] for i in range(max(len(t) - 1, 1)))
                chunk_grams = grams(chunk)
                near = any(
                    len(chunk_grams & g) / max(1, len(chunk_grams | g)) >= 0.95
                    for g in recent_grams
                )
                vector = None
                if semantic and len(accepted) + len(rejected) < 32 and sha not in seen:
                    try:
                        raw = self.s.memory.embed(chunk)
                        vector = np.frombuffer(raw, dtype="<f4")
                        near = near or any(
                            v.shape == vector.shape and float(v @ vector) >= 0.98
                            for v in previous_vectors
                        )
                    except Exception:
                        semantic = False
                        semantic_status = "unavailable_lexical_fallback"
                if sha in seen or near:
                    rejected.append(
                        {
                            "sha256": sha,
                            "reason": "duplicate" if sha in seen else "near_duplicate",
                        }
                    )
                else:
                    accepted.append({"content": chunk, "sha256": sha})
                    seen.add(sha)
                    if vector is not None:
                        self._vectors[sha] = vector.tobytes()
                        previous_vectors.append(vector)
                    recent_grams.append(chunk_grams)
                    recent_grams = recent_grams[-32:]
                if len(accepted) + len(rejected) > 10000:
                    raise ValueError("too many chunks")
        return {
            "title": title.strip(),
            "characters": len(text),
            "sha256": digest(normalized),
            "accepted": accepted,
            "rejected": rejected,
            "semantic_status": semantic_status,
            "semantic_chunk_limit": 32,
        }

    @staticmethod
    def validate_filename(filename):
        if (
            not isinstance(filename, str)
            or not 1 <= len(filename) <= 200
            or "/" in filename
            or "\\" in filename
            or ".." in filename
            or "\x00" in filename
            or PurePosixPath(filename).suffix.lower() not in (".txt", ".md")
        ):
            raise ValueError("invalid filename")

    def preview_file(self, filename, stream, size):
        self.validate_filename(filename)
        if type(size) is not int or not 0 < size <= MAX_BYTES:
            raise ValueError("invalid file size")
        raw = stream.read(size + 1)
        if len(raw) != size:
            raise ValueError("partial or oversized upload")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeError:
            raise ValueError("UTF-8 required") from None
        return self.preview_text(filename, text)

    def prepare(self, p):
        if set(p) == {"remove_source_id"}:
            if type(p["remove_source_id"]) is not int:
                raise ValueError("invalid source")
            row = self.s.conn.execute(
                "SELECT id,title FROM knowledge_sources WHERE id=?",
                (p["remove_source_id"],),
            ).fetchone()
            if not row:
                raise ValueError("source missing")
            return (
                self.snapshot(p),
                [{"field": "knowledge.source", "before": dict(row), "after": None}],
                ["移除该知识来源及其切片，不可撤销；用户记忆不变。"],
            )
        if set(p) != {"title", "text"}:
            raise ValueError("invalid import")
        preview = self.preview_text(p["title"], p["text"])
        if not preview["accepted"]:
            raise ValueError("no new chunks")
        # Pin the exact reviewed chunks: a provider outage before confirmation
        # must never silently change the import that was approved.
        p["prepared_preview"] = preview
        p.pop("text")
        return (
            self.snapshot(p),
            [
                {
                    "field": "knowledge.import",
                    "before": None,
                    "after": {
                        "title": preview["title"],
                        "characters": preview["characters"],
                        "chunks": len(preview["accepted"]),
                        "duplicates": len(preview["rejected"]),
                    },
                }
            ],
            ["知识文本按不可信资料处理，不会成为用户画像或系统指令。"],
        )

    def execute_import(self, preview):
        row = self.s.conn.execute(
            "INSERT INTO knowledge_sources(title,sha256,created_at) VALUES(?,?,?)",
            (preview["title"], preview["sha256"], time.time()),
        )
        for chunk in preview["accepted"]:
            vector = self._vectors.get(chunk["sha256"])
            self.s.conn.execute(
                "INSERT INTO knowledge_chunks(source_id,content,sha256,content_vector,embedding_model) VALUES(?,?,?,?,?)",
                (
                    row.lastrowid,
                    chunk["content"],
                    chunk["sha256"],
                    vector,
                    self.s.memory._embedder.model_id if vector is not None else None,
                ),
            )
        return {
            "source_id": row.lastrowid,
            "chunks": len(preview["accepted"]),
            "title": preview["title"],
        }

    def execute(self, p):
        if "remove_source_id" in p:
            self.s.conn.execute(
                "DELETE FROM knowledge_chunks WHERE source_id=?",
                (p["remove_source_id"],),
            )
            self.s.conn.execute(
                "DELETE FROM knowledge_sources WHERE id=?", (p["remove_source_id"],)
            )
            return {"removed_source_id": p["remove_source_id"]}
        preview = p["prepared_preview"]
        self._vectors = {}
        if self.s.memory._embedder is not None:
            for chunk in preview["accepted"][:32]:
                try:
                    self._vectors[chunk["sha256"]] = self.s.memory.embed(
                        chunk["content"]
                    )
                except Exception:
                    break
        return self.execute_import(preview)

    def search(self, query, *, limit=8):
        if (
            not isinstance(query, str)
            or not 1 <= len(query.strip()) <= 200
            or type(limit) is not int
            or not 1 <= limit <= 50
        ):
            raise ValueError("invalid search")
        query = query.strip()
        terms = re.findall(r"[A-Za-z0-9_]{2,}", query.lower())
        for word in re.findall(r"[\u4e00-\u9fff]+", query):
            terms.extend(
                [word]
                if len(word) < 3
                else [word[i : i + 2] for i in range(len(word) - 1)]
            )
        terms = list(dict.fromkeys([query.lower()] + terms))[:20]
        escaped = (
            lambda x: x.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        condition = " OR ".join(
            "(c.content LIKE ? ESCAPE char(92) OR s.title LIKE ? ESCAPE char(92))"
            for _ in terms
        )
        params = [f"%{escaped(t)}%" for t in terms for _ in range(2)]
        rows = self.s.conn.execute(
            "SELECT c.id,c.source_id,c.content,s.title FROM knowledge_chunks c JOIN knowledge_sources s ON c.source_id=s.id WHERE "
            + condition
            + " ORDER BY c.id DESC LIMIT 200",
            params,
        ).fetchall()
        scores = {
            r["id"]: (
                sum(t in (r["title"] + " " + r["content"]).lower() for t in terms),
                dict(r),
            )
            for r in rows
        }
        provider = self.s.memory._embedder
        if provider is not None:
            try:
                vector = np.frombuffer(self.s.memory.embed(query), dtype="<f4")
                for r in self.s.conn.execute(
                    "SELECT c.id,c.source_id,c.content,c.content_vector,s.title FROM knowledge_chunks c JOIN knowledge_sources s ON c.source_id=s.id WHERE c.embedding_model=? AND c.content_vector IS NOT NULL LIMIT 5000",
                    (provider.model_id,),
                ):
                    v = np.frombuffer(r["content_vector"], dtype="<f4")
                    if v.shape == vector.shape and float(v @ vector) >= 0.65:
                        score = (
                            scores.get(r["id"], (0, None))[0] + float(v @ vector) * 2
                        )
                        scores[r["id"]] = (
                            score,
                            {k: r[k] for k in ("id", "source_id", "content", "title")},
                        )
            except Exception:
                pass
        ranked = sorted(scores.values(), key=lambda x: (-x[0], -x[1]["id"]))[:limit]
        return [row | {"untrusted": True} for score, row in ranked]

    def reverse(self, before, after):
        if "source_id" not in after:
            from .operations import OperationError

            raise OperationError(422, "not_reversible")
        return {"remove_source_id": after["source_id"]}
