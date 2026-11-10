"""Single-user loopback management UI. Run: python -m avatar.web."""

from __future__ import annotations

import argparse
import json
import secrets
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlsplit, unquote

from .brain.emotion import EmotionEngine
from .brain.boundaries import BoundaryPolicy
from .brain.memory import MemoryStore
from .brain.reminders import ReminderStore
from .brain.summaries import SummaryStore


def _public(row):
    return (
        {k: v for k, v in row.items() if k != "content_vector"}
        if row is not None
        else None
    )


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status, data, *, html=False, content_type=None):
        if (
            self.path.startswith("/api/v1/")
            and isinstance(data, dict)
            and "request_id" not in data
        ):
            error = data.get("error")
            data = {
                "data": None if error else data,
                "error": (
                    {"code": "request_rejected", "message": error} if error else None
                ),
                "request_id": getattr(self, "request_id", secrets.token_hex(12)),
            }
        body = (
            data
            if isinstance(data, bytes)
            else (
                data.encode("utf-8")
                if html
                else json.dumps(data, ensure_ascii=False, allow_nan=False).encode(
                    "utf-8"
                )
            )
        )
        self.send_response(status)
        self.send_header(
            "Content-Type",
            content_type
            or (
                "text/html; charset=utf-8"
                if html
                else "application/json; charset=utf-8"
            ),
        )
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; font-src 'self'; base-uri 'none'; object-src 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def _request(self, post=False):
        self.request_id = secrets.token_hex(12)
        expected_host = f"127.0.0.1:{self.server.server_port}"
        if self.headers.get("Host") != expected_host:
            return self._send(403, {"error": "invalid host"})
        origin = self.headers.get("Origin")
        if origin and origin != "http://" + expected_host:
            return self._send(403, {"error": "invalid origin"})
        parsed = urlsplit(self.path)
        if not parsed.path.startswith("/api/"):
            if not post:
                return self._static(parsed.path)
            return self._send(404, {"error": "not found"})
        token = self.headers.get("X-Avatar-Token", "")
        if not secrets.compare_digest(token.encode(), self.server.token.encode()):
            return self._send(403, {"error": "请使用启动终端提供的完整链接打开页面。"})
        memory = None
        try:
            data = {}
            if post:
                if parsed.path == "/api/v1/knowledge/preview-file":
                    return self._knowledge_upload(parsed)
                if self.headers.get_content_type() != "application/json":
                    raise ValueError("Content-Type must be application/json")
                if (
                    self.headers.get("Transfer-Encoding")
                    or len(self.headers.get_all("Content-Length", [])) != 1
                ):
                    raise ValueError("single Content-Length required")
                length = int(self.headers.get("Content-Length", "0"))
                limit = (
                    (5 * 1024 * 1024 + 4096)
                    if parsed.path == "/api/v1/knowledge/preview-text"
                    else 16384
                )
                if not 0 < length <= limit:
                    raise ValueError("request body must be 1..16384 bytes")
                self.connection.settimeout(5)
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise ValueError("incomplete body")
                data = json.loads(raw.decode("utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("JSON object required")
            if parsed.path.startswith("/api/v1/"):
                from .web_api import V1API
                from .brain.operations import OperationError

                memory = MemoryStore(
                    self.server.db_path, embedder=self.server.knowledge_embedder
                )
                try:
                    code, result = V1API(self.server, memory, self._chat).handle(
                        post,
                        parsed.path[len("/api/v1") :],
                        parse_qs(parsed.query),
                        data,
                    )
                    return self._send(
                        code,
                        {"data": result, "error": None, "request_id": self.request_id},
                    )
                except OperationError as exc:
                    return self._send(
                        exc.status,
                        {
                            "data": None,
                            "error": {"code": exc.code, "message": exc.message},
                            "request_id": self.request_id,
                        },
                    )
                except (ValueError, TypeError, KeyError):
                    return self._send(
                        422,
                        {
                            "data": None,
                            "error": {
                                "code": "invalid_request",
                                "message": "请检查输入字段、范围或文件格式。",
                            },
                            "request_id": self.request_id,
                        },
                    )
            if post and not self.server.legacy_writes:
                return self._send(
                    410,
                    {"error": "旧写入接口已关闭，请使用带预览和确认的 /api/v1 接口。"},
                )

            def ident():
                value = data.get("id")
                if type(value) is not int or value <= 0:
                    raise ValueError("positive integer id required")
                return value

            def text(field):
                value = data.get(field)
                if not isinstance(value, str) or not value.strip() or len(value) > 4000:
                    raise ValueError("non-empty text up to 4000 characters required")
                return value.strip()

            path = parsed.path
            if post and path == "/api/chat":
                user_text = text("text")
                use_web = data.get("use_web", False)
                if type(use_web) is not bool:
                    raise ValueError("use_web must be boolean")
                return self._send(200, self._chat(user_text, use_web))
            memory = MemoryStore(self.server.db_path)
            reminders = ReminderStore(memory)
            query = parse_qs(parsed.query)
            if not post and path == "/api/memories":
                result = {
                    "memories": [
                        _public(row) | {"strength": memory.memory_strength(row)}
                        for row in memory.list_memories(
                            include_history=query.get("history") == ["1"], limit=5000
                        )
                    ]
                }
            elif not post and path == "/api/memory":
                result = {
                    "memory": _public(memory.inspect(int(query.get("id", ["0"])[0])))
                }
            elif not post and path == "/api/reminders":
                result = {"reminders": reminders.list()}
            elif not post and path == "/api/summary":
                result = {"summary": SummaryStore(memory).read(self.server.session_id)}
            elif not post and path == "/api/state":
                with self.server.state_lock:
                    state = self.server.emotion.state
                    result = {
                        "energy": self.server.emotion.energy,
                        "valence": state.valence,
                        "arousal": state.arousal,
                        "mode": "单用户本机模式",
                    }
            elif post and path == "/api/correct":
                result = {"id": memory.correct(ident(), text("content"))}
                with self.server.state_lock:
                    self.server.short_term = []
            elif post and path == "/api/forget":
                memory.forget(ident())
                with self.server.state_lock:
                    self.server.short_term = []
                result = {"ok": True}
            elif post and path == "/api/forget-summary-source":
                SummaryStore(memory).forget_source(self.server.session_id, ident())
                with self.server.state_lock:
                    self.server.short_term = []
                result = {"ok": True}
            elif post and path == "/api/badhit":
                memory.report_irrelevant(ident())
                result = {"ok": True}
            elif post and path == "/api/reminders":
                result = {"reminder": reminders.create(text("text"))}
            elif post and path == "/api/reminder-status":
                reminders.set_status(ident(), text("status"))
                result = {"ok": True}
            elif post and path == "/api/delete-reminder":
                reminders.delete(ident())
                result = {"ok": True}
            elif post and path == "/api/due":
                result = {"reminders": reminders.claim_due()}
            else:
                return self._send(404, {"error": "not found"})
            self._send(200, result)
        except (ValueError, TypeError, UnicodeError) as exc:
            self._send(400, {"error": str(exc)})
        except Exception:
            self._send(500, {"error": "操作失败，请检查数据库或模型服务。"})
        finally:
            if memory is not None:
                memory.close()

    def do_GET(self):
        self._request()

    def do_POST(self):
        self._request(post=True)

    def _chat(self, user_text, use_web=False):
        from .main import Avatar

        with self.server.state_lock:
            avatar = Avatar(db_path=self.server.db_path, session_id=self.server.session_id)
            memory = avatar.memory
            try:
                avatar.emotion = self.server.emotion
                avatar.boundaries = self.server.boundaries
                if self.server.context_revision != memory.context_revision:
                    self.server.short_term = []
                for message in self.server.short_term:
                    memory.add_short_term(message["role"], message["content"])
                result = avatar.respond(user_text, use_web=use_web)
                self.server.short_term = memory.get_short_term()
                self.server.context_revision = memory.context_revision
                return result
            finally:
                memory.close()

    def _knowledge_upload(self, parsed):
        from .brain.knowledge import KnowledgeService, MAX_BYTES
        from .brain.admin_store import AdminStore, initial_persona
        from .brain.operations import OperationService

        query = parse_qs(parsed.query)
        filename = query.get("filename", [""])[0]
        length = int(self.headers.get("Content-Length", "0"))
        try:
            KnowledgeService.validate_filename(filename)
        except ValueError:
            return self._send(422, {"error": "文件名无效；仅支持.txt和.md。"})
        expected_mime = (
            "text/markdown" if filename.lower().endswith(".md") else "text/plain"
        )
        if (
            set(query) != {"filename"}
            or len(query["filename"]) != 1
            or self.headers.get("Transfer-Encoding")
            or len(self.headers.get_all("Content-Length", [])) != 1
            or not 0 < length <= MAX_BYTES
            or self.headers.get_content_type() != expected_mime
        ):
            return self._send(422, {"error": "仅接受不超过5 MiB的UTF-8 .txt/.md文件。"})
        self.connection.settimeout(5)
        raw = self.rfile.read(length)
        with_memory = MemoryStore(
            self.server.db_path, embedder=self.server.knowledge_embedder
        )
        try:
            store = AdminStore(with_memory)
            store.migrate(initial_persona())
            KnowledgeService.validate_filename(filename)
            if len(raw) != length:
                raise ValueError("incomplete upload")
            text = raw.decode("utf-8-sig")
            draft = OperationService(store).create_draft(
                "knowledge.import", {"title": filename, "text": text}
            )
            preview = json.loads(
                store.conn.execute(
                    "SELECT parameters_json FROM operation_drafts WHERE id=?",
                    (draft.draft_id,),
                ).fetchone()[0]
            )["prepared_preview"]
            return self._send(
                201,
                {
                    "data": {"preview": preview, "draft": draft.data()},
                    "error": None,
                    "request_id": self.request_id,
                },
            )
        except (ValueError, UnicodeError, TypeError):
            return self._send(
                422,
                {"error": "文件解析失败或没有可导入的新内容；仅接受有效UTF-8文本。"},
            )
        finally:
            with_memory.close()

    def _static(self, path):
        root = self.server.frontend_dir
        decoded = unquote(path)
        if (
            any(part in (".", "..") for part in decoded.split("/"))
            or "%" in decoded
            or "\\" in decoded
        ):
            return self._send(404, {"error": "not found"})
        if decoded.startswith("/assets/"):
            target = (root / decoded.lstrip("/")).resolve()
            types = {
                ".js": "text/javascript; charset=utf-8",
                ".css": "text/css; charset=utf-8",
                ".svg": "image/svg+xml",
                ".png": "image/png",
                ".woff2": "font/woff2",
                ".ico": "image/x-icon",
            }
            if (
                not target.is_relative_to(root)
                or not target.is_relative_to(root / "assets")
                or target.suffix not in types
                or not target.is_file()
            ):
                return self._send(404, {"error": "not found"})
            return self._send(
                200, target.read_bytes(), content_type=types[target.suffix]
            )
        if decoded not in {
            "/",
            "/chat",
            "/persona",
            "/emotion",
            "/memory",
            "/knowledge",
            "/reminders",
            "/tools",
            "/audit",
        }:
            return self._send(404, {"error": "not found"})
        try:
            index = root / "index.html"
            if not index.resolve().is_relative_to(root):
                raise ValueError("invalid index")
            content = index.read_text(encoding="utf-8")
            for asset in re.findall(
                r"(?:src|href)=[\"\'](/assets/[^\"\']+)[\"\']", content
            ):
                target = (root / asset.lstrip("/")).resolve()
                if not target.is_relative_to(root) or not target.is_file():
                    raise ValueError("missing asset")
            if "<html" not in content.lower():
                raise ValueError("invalid index")
        except (OSError, UnicodeError, ValueError):
            content = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>Mission Control 安装</title><body><h1>前端尚未构建</h1><p>在项目目录执行 npm --prefix frontend ci，然后执行 npm --prefix frontend run build，再刷新。</p></body></html>'
        return self._send(200, content, html=True)


def create_server(
    db_path: str,
    *,
    port: int = 8765,
    frontend_dir: str | Path | None = None,
    legacy_writes: bool = True,
    knowledge_embedder=None,
) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    server.db_path = db_path
    server.legacy_writes = legacy_writes
    server.knowledge_embedder = knowledge_embedder
    server.chat_events = []
    server.frontend_dir = Path(
        frontend_dir or Path(__file__).resolve().parents[2] / "frontend/dist"
    ).resolve()
    server.token = secrets.token_urlsafe(32)
    server.nonce = secrets.token_urlsafe(24)
    server.session_id = secrets.token_hex(16)
    server.short_term = []
    server.context_revision = None
    server.emotion = EmotionEngine()
    server.boundaries = BoundaryPolicy()
    return server


def main():
    from .config import config

    parser = argparse.ArgumentParser(description="Avatar 单用户本机管理页面")
    parser.add_argument("--db", default=config.memory_db_path)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    from .brain.embeddings import OllamaEmbeddingProvider

    embedder = (
        OllamaEmbeddingProvider(
            config.embedding.base_url, config.embedding.model, config.embedding.timeout
        )
        if config.embedding.model
        else None
    )
    server = create_server(
        args.db, port=args.port, legacy_writes=False, knowledge_embedder=embedder
    )
    print(
        f"本机管理页面：http://127.0.0.1:{server.server_port}/#{server.token}",
        flush=True,
    )
    print("保持程序和页面运行以轮询提醒；当前为单用户模式。Ctrl+C 退出。", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
