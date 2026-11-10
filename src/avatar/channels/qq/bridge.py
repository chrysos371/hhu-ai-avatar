"""Bounded async ingress, durable de-duplication and conservative delivery states."""

from __future__ import annotations
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from functools import partial
import os
import logging
from pathlib import Path
import sqlite3
import time
from .engine import AvatarEngine
from .policy import ReplyPolicy
from .protocol import digest


@dataclass(frozen=True)
class Outcome:
    status: str
    receipt_key: str


class InstanceLock:
    def __init__(self, path):
        self.file = Path(path).open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                self.file.seek(0)
                self.file.write(b"0")
                self.file.flush()
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close()
            raise RuntimeError("QQ state directory is already in use") from None

    def close(self):
        self.file.close()


class Receipts:
    def __init__(self, path):
        self.path = Path(path)
        with self.connection() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS receipts (key TEXT PRIMARY KEY,fingerprint TEXT NOT NULL,status TEXT NOT NULL,updated_at REAL NOT NULL)"
            )
            # A network call may have completed before a process crash: never blindly resend it.
            conn.execute(
                "UPDATE receipts SET status='generation_failed' WHERE status='processing'"
            )
            conn.execute(
                "UPDATE receipts SET status='delivery_unknown' WHERE status='sending'"
            )
            conn.execute("CREATE TABLE IF NOT EXISTS qq_admissions (receipt TEXT PRIMARY KEY, scope TEXT NOT NULL, admitted REAL NOT NULL)")
            conn.execute("CREATE INDEX IF NOT EXISTS qq_admissions_scope ON qq_admissions(scope, admitted)")
        self.path.chmod(0o600)

    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.path, timeout=5)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def claim(self, m, now, policy=None):
        with self.connection() as c:
            c.execute("BEGIN IMMEDIATE")
            old = c.execute(
                "SELECT fingerprint,status FROM receipts WHERE key=?", (m.receipt_key,)
            ).fetchone()
            if old:
                if old[0] != m.fingerprint:
                    return "collision"
                if old[1] != "generation_failed":
                    return old[1]
                c.execute(
                    "UPDATE receipts SET status='processing',updated_at=? WHERE key=?",
                    (now, m.receipt_key),
                )
            else:
                if policy is not None and m.kind == "group":
                    if policy.quiet(now):
                        return "quiet_hours"
                    scope = digest([m.bot_id, m.kind, m.target])
                    c.execute("DELETE FROM qq_admissions WHERE admitted < ?", (now - 3600,))
                    times = [r[0] for r in c.execute(
                        "SELECT admitted FROM qq_admissions WHERE scope=?", (scope,))]
                    if (len(times) >= policy.group_per_hour or
                        sum(t > now - 60 for t in times) >= policy.group_per_minute or
                        (times and now - max(times) < policy.group_cooldown)):
                        return "rate_limited"
                    c.execute("INSERT INTO qq_admissions VALUES(?,?,?)",
                              (m.receipt_key, scope, now))
                c.execute(
                    "INSERT INTO receipts VALUES(?,?,'processing',?)",
                    (m.receipt_key, m.fingerprint, now),
                )
        return "claimed"

    def move(self, key, before, after, now):
        with self.connection() as c:
            return (
                c.execute(
                    "UPDATE receipts SET status=?,updated_at=? WHERE key=? AND status=?",
                    (after, now, key, before),
                ).rowcount
                == 1
            )


class QQBridge:
    def __init__(
        self,
        root,
        *,
        engine=None,
        clock=time.time,
        max_age=120,
        workers=4,
        max_pending=32,
        policy=None,
    ):
        if (
            not 1 <= workers <= 8
            or not workers <= max_pending <= 128
            or not 10 <= max_age <= 240
        ):
            raise ValueError("Invalid QQ resource limits")
        self.policy = policy if policy is not None else ReplyPolicy.environment()
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        self.instance = InstanceLock(self.root / "service.lock")
        try:
            self.receipts = Receipts(self.root / "receipts.db")
        except BaseException:
            self.instance.close()
            raise
        self.engine = engine or AvatarEngine()
        self.clock = clock
        self.max_age = max_age
        self.max_pending = max_pending
        self.pool = ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="avatar-qq"
        )
        self.pending = 0
        self.contexts = {}
        self.closed = False

    async def work(self, fn, *args):
        future = asyncio.get_running_loop().run_in_executor(
            self.pool, partial(fn, *args)
        )
        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            # Do not release this conversation's lock while its worker still writes.
            try:
                await asyncio.shield(future)
            except Exception:
                pass
            raise

    def fresh(self, m):
        return -30 <= self.clock() - m.occurred_at <= self.max_age

    def generate(self, m):
        if not self.fresh(m):
            return "expired", None
        status = self.receipts.claim(m, self.clock(), self.policy)
        if status != "claimed":
            return status, None
        if not self.fresh(m):
            self.receipts.move(m.receipt_key, "processing", "expired", self.clock())
            return "expired", None
        try:
            reply = self.engine.respond(m, self.root / "contexts" / m.context_key)
            self.receipts.move(m.receipt_key, "processing", "ready", self.clock())
            return "ready", reply
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "QQ generation failed type=%s receipt=%s",
                type(exc).__name__,
                m.receipt_key[:12],
            )
            self.receipts.move(
                m.receipt_key, "processing", "generation_failed", self.clock()
            )
            return "generation_failed", None

    def replay_ready(self, m):
        # Read the per-context cache; a ready receipt must never generate a new reply.
        path = self.root / "contexts" / m.context_key / "memory.db"
        if not path.exists():
            raise ValueError("Reply cache unavailable")
        c = sqlite3.connect(path)
        try:
            row = c.execute(
                "SELECT reply FROM qq_replies WHERE receipt_key=?", (m.receipt_key,)
            ).fetchone()
            if not row:
                raise ValueError("Reply cache unavailable")
            return row[0]
        finally:
            c.close()

    async def handle(self, m, send):
        if self.closed:
            return Outcome("closed", m.receipt_key)
        if self.pending >= self.max_pending or (
            m.context_key in self.contexts and self.contexts[m.context_key][1] >= 4
        ):
            return Outcome("busy", m.receipt_key)
        self.pending += 1
        if m.context_key not in self.contexts:
            self.contexts[m.context_key] = [asyncio.Lock(), 0]
        entry = self.contexts[m.context_key]
        entry[1] += 1
        try:
            async with entry[0]:
                status, reply = await self.work(self.generate, m)
                if status != "ready":
                    return Outcome(status, m.receipt_key)
                if reply is None:
                    try:
                        reply = await self.work(self.replay_ready, m)
                    except Exception:
                        await self.work(
                            self.receipts.move,
                            m.receipt_key,
                            "ready",
                            "generation_unknown",
                            self.clock(),
                        )
                        return Outcome("generation_unknown", m.receipt_key)
                if not self.fresh(m):
                    await self.work(
                        self.receipts.move,
                        m.receipt_key,
                        "ready",
                        "expired",
                        self.clock(),
                    )
                    return Outcome("expired", m.receipt_key)
                changed = await self.work(
                    self.receipts.move, m.receipt_key, "ready", "sending", self.clock()
                )
                if not changed:
                    return Outcome("duplicate", m.receipt_key)
                try:
                    await asyncio.wait_for(send(m, reply), timeout=20)
                except asyncio.CancelledError:
                    await self.work(
                        self.receipts.move,
                        m.receipt_key,
                        "sending",
                        "delivery_unknown",
                        self.clock(),
                    )
                    raise
                except Exception:
                    await self.work(
                        self.receipts.move,
                        m.receipt_key,
                        "sending",
                        "delivery_unknown",
                        self.clock(),
                    )
                    return Outcome("delivery_unknown", m.receipt_key)
                await self.work(
                    self.receipts.move, m.receipt_key, "sending", "sent", self.clock()
                )
                return Outcome("sent", m.receipt_key)
        finally:
            self.pending -= 1
            entry[1] -= 1
            if entry[1] == 0:
                self.contexts.pop(m.context_key, None)

    async def close(self):
        self.closed = True
        while self.pending:
            await asyncio.sleep(0.01)
        await asyncio.to_thread(self.pool.shutdown, wait=True)
        self.instance.close()
