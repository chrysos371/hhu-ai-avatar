"""Bounded single-user turn jobs with replayable events and durable deduplication."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
import hashlib
import json
import re
import sqlite3
import threading
import time

from .brain.operations import OperationError
from .cancellation import CancellationToken, Cancelled


@dataclass
class Turn:
    id: str
    text: str
    use_web: bool
    created_at: float = field(default_factory=time.time)
    status: str = 'queued'
    events: list = field(default_factory=list)
    result: dict | None = None
    token: CancellationToken = field(default_factory=CancellationToken)
    changed: threading.Condition = field(default_factory=threading.Condition)
    subscribers: int = 0
    redacted: bool = False

    def emit(self, kind, data):
        with self.changed:
            if self.redacted:
                return
            if kind == 'text' and len(self.events) >= 500:
                return
            self.events.append({'id': len(self.events), 'event': kind, 'data': data})
            self.changed.notify_all()

    def public(self):
        return {'job_id': self.id, 'status': self.status, 'created_at': self.created_at,
                'result': self.result if self.status == 'completed' else None}


class TurnCoordinator:
    def __init__(self, db_path, runner, *, ttl=900, max_jobs=32):
        self.db_path, self.runner = db_path, runner
        self.ttl, self.max_jobs = ttl, max_jobs
        self._lock = threading.Lock()
        self._jobs = OrderedDict()
        self._active = None
        self._thread = None
        self._closed = False

    @staticmethod
    def validate(data):
        if (not isinstance(data, dict) or not set(data) <= {'request_id', 'text', 'use_web'}
                or not isinstance(data.get('request_id'), str)
                or not re.fullmatch(r'[A-Za-z0-9_-]{20,100}', data['request_id'])
                or not isinstance(data.get('text'), str) or not 1 <= len(data['text'].strip()) <= 4000
                or type(data.get('use_web', False)) is not bool):
            raise OperationError(422, 'invalid_turn', '消息或请求编号无效。')
        return data['request_id'], data['text'].strip(), data.get('use_web', False)

    def _ledger(self, request_id, fingerprint, status=None):
        with sqlite3.connect(self.db_path, timeout=5) as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS runtime_turn_ledger (
                request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
                status TEXT NOT NULL, created_at REAL NOT NULL)''')
            if status is not None:
                conn.execute('UPDATE runtime_turn_ledger SET status=? WHERE request_id=?', (status, request_id))
                return
            row = conn.execute('SELECT fingerprint FROM runtime_turn_ledger WHERE request_id=?', (request_id,)).fetchone()
            if row:
                if row[0] != fingerprint:
                    raise OperationError(409, 'request_id_conflict', '请求编号已用于另一条消息。')
                raise OperationError(410, 'turn_expired', '此请求已接收，运行记录已过期或进程已重启；不会重复执行。')
            conn.execute('INSERT INTO runtime_turn_ledger VALUES (?,?,?,?)',
                         (request_id, fingerprint, 'queued', time.time()))

    def submit(self, data):
        request_id, text, use_web = self.validate(data)
        fingerprint = hashlib.sha256(json.dumps([text, use_web], ensure_ascii=False).encode()).hexdigest()
        with self._lock:
            if self._closed:
                raise OperationError(503, 'runtime_closed', '对话服务正在关闭。')
            self._prune_locked()
            if request_id in self._jobs:
                job = self._jobs[request_id]
                if (job.text, job.use_web) != (text, use_web):
                    raise OperationError(409, 'request_id_conflict', '请求编号已用于另一条消息。')
                return job
            if self._active is not None:
                raise OperationError(409, 'turn_busy', '正在处理上一条消息，请先停止或等待完成。')
            while len(self._jobs) >= self.max_jobs:
                _, old = self._jobs.popitem(last=False)
                self._redact(old, 'expired')
            self._ledger(request_id, fingerprint)
            job = Turn(request_id, text, use_web)
            job.emit('status', {'status': 'queued'})
            self._jobs[request_id] = job
            self._active = job
            self._thread = threading.Thread(target=self._run, args=(job,), daemon=True)
            self._thread.start()
            return job

    def _run(self, job):
        status, kind, data = 'failed', 'error', {'code': 'turn_failed', 'message': '本轮处理失败，已接收的消息不会自动重试。'}
        result = None
        try:
            with job.changed:
                job.status = 'running'
                job.emit('status', {'status': 'running'})
            result = self.runner(job)
            status, kind, data = 'completed', 'result', result
        except Cancelled:
            status, kind, data = 'cancelled', 'cancelled', {'status': 'cancelled'}
        except Exception:
            pass
        finally:
            try:
                self._ledger(job.id, '', status=status)
            except sqlite3.Error:
                # The request ID was inserted before execution, so retries still cannot replay it.
                pass
            with self._lock:
                if self._active is job:
                    self._active = None
            with job.changed:
                if job.redacted:
                    return
                job.result, job.status = result, status
                job.emit(kind, data)

    def get(self, job_id):
        with self._lock:
            self._prune_locked()
            job = self._jobs.get(job_id)
            if job is None:
                raise OperationError(404, 'turn_not_found', '本轮记录不存在或已过期。')
            return job

    @staticmethod
    def _redact(job, status):
        with job.changed:
            job.redacted = True
            job.text, job.result = '', None
            job.events.clear()
            job.status = status
            job.changed.notify_all()

    def _prune_locked(self):
        for key in list(self._jobs):
            job = self._jobs[key]
            if job.status in ('completed', 'cancelled', 'failed') and job.created_at + self.ttl <= time.time():
                self._redact(job, 'expired')
                del self._jobs[key]

    def cancel(self, job_id):
        job = self.get(job_id)
        if job.status not in ('completed', 'cancelled', 'failed'):
            job.token.cancel()
        return job.public()

    def close(self):
        with self._lock:
            self._closed = True
            job, thread = self._active, self._thread
        if job:
            job.token.cancel()
        if thread:
            thread.join(timeout=2)
