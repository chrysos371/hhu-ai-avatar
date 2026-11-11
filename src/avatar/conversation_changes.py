"""Bounded metadata waits; optional source cursor, one idle-aware DB monitor."""
from contextlib import closing
from pathlib import Path
import sqlite3
import threading
import time

from .brain.operations import OperationError


class WatchDisconnected(Exception):
    pass


class ConversationChanges:
    def __init__(self, db_path, instance_id, *, limit=4, heartbeat=10.0, poll_interval=.1):
        self.db_path, self.instance_id = db_path, instance_id
        self.limit, self.heartbeat, self.poll_interval = limit, heartbeat, poll_interval
        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._thread = None
        self._active = 0
        self._revision = 0
        self._context_cursor = 0
        self._track_context = False
        self._error = False
        self._failure_epoch = 0
        self._seen_database = False
        self.monitor_checks = 0

    @property
    def active_count(self):
        with self._condition:
            return self._active

    def _read_revision(self):
        if self.db_path == ':memory:':
            return 0
        path = Path(self.db_path).resolve()
        if not path.exists() and not self._seen_database:
            return 0
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=.5)) as conn:
            row = conn.execute('SELECT revision FROM memory_context_revision WHERE id=1').fetchone()
            if row is None or type(row[0]) is not int or row[0] < 0:
                raise sqlite3.DatabaseError('invalid context revision')
            self._seen_database = True
            return row[0]

    def _read_state(self):
        if self.db_path == ':memory:':
            return 0, 0
        path = Path(self.db_path).resolve()
        if not path.exists() and not self._seen_database:
            return 0, 0
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=.5)) as conn:
            row = conn.execute("SELECT revision,(SELECT COALESCE(MAX(id),0) FROM memory_messages WHERE role='user') "
                               'FROM memory_context_revision WHERE id=1').fetchone()
            if row is None or any(type(value) is not int or value < 0 for value in row):
                raise sqlite3.DatabaseError('invalid context state')
            self._seen_database = True
            return tuple(row)

    def publish(self, revision, *, context_cursor=None, _read_epoch=None):
        if (type(revision) is not int or revision < 0
                or (context_cursor is not None and (type(context_cursor) is not int or context_cursor < 0))):
            raise ValueError('nonnegative integer version required')
        with self._condition:
            if self._stop.is_set():
                return
            # A successful read already in flight when an error was observed
            # cannot certify recovery. Require a read started after that error.
            if _read_epoch is not None and _read_epoch != self._failure_epoch:
                return
            # Concurrent checks may finish in the opposite order to their DB
            # reads. A late old value must never lower the advertised version.
            changed = (revision > self._revision or self._error
                       or (context_cursor is not None and context_cursor > self._context_cursor))
            self._revision = max(self._revision, revision)
            if context_cursor is not None:
                self._context_cursor = max(self._context_cursor, context_cursor)
            self._error = False
            if changed:
                self._condition.notify_all()

    def check(self):
        with self._condition:
            if self._stop.is_set():
                return
            epoch = self._failure_epoch
            context = self._track_context
        try:
            if context:
                revision, cursor = self._read_state()
                self.publish(revision, context_cursor=cursor, _read_epoch=epoch)
            else:
                self.publish(self._read_revision(), _read_epoch=epoch)
        except sqlite3.Error:
            with self._condition:
                if self._stop.is_set():
                    return
                self._failure_epoch += 1
                self._error = True
                self._condition.notify_all()

    def _monitor(self):
        while not self._stop.is_set():
            with self._condition:
                self._condition.wait_for(lambda: self._active > 0 or self._stop.is_set())
                if self._stop.is_set():
                    return
            self.monitor_checks += 1
            self.check()
            # API notifications wake waiters, but cannot accelerate this shared
            # external-connection polling loop beyond the fixed interval.
            self._stop.wait(self.poll_interval)

    def wait(self, instance_id, revision, *, context_cursor=None, disconnected=lambda: False):
        if context_cursor is not None:
            if type(context_cursor) is not int or context_cursor < 0:
                raise ValueError('nonnegative integer context cursor required')
            with self._condition:
                self._track_context = True
        self.check()
        with self._condition:
            def metadata():
                value = {'instance_id': self.instance_id, 'revision': self._revision}
                if context_cursor is not None: value['context_cursor'] = self._context_cursor
                return value
            if self._stop.is_set():
                raise OperationError(503, 'runtime_closed', '版本服务正在关闭。')
            if self._error:
                raise OperationError(503, 'revision_unavailable', '暂时无法核验对话版本。')
            if (instance_id != self.instance_id or revision != self._revision
                    or (context_cursor is not None and context_cursor != self._context_cursor)):
                return metadata()
            if self._active >= self.limit:
                raise OperationError(429, 'watch_capacity', '版本等待连接已满，请稍后重试。')
            self._active += 1
            if self._thread is None:
                self._thread = threading.Thread(target=self._monitor, name='avatar-conversation-watch', daemon=True)
                self._thread.start()
            self._condition.notify_all()
            deadline = time.monotonic() + self.heartbeat
            try:
                while True:
                    if disconnected():
                        raise WatchDisconnected()
                    if self._stop.is_set():
                        raise OperationError(503, 'runtime_closed', '版本服务正在关闭。')
                    if self._error:
                        raise OperationError(503, 'revision_unavailable', '暂时无法核验对话版本。')
                    remaining = deadline - time.monotonic()
                    if (revision != self._revision or remaining <= 0
                            or (context_cursor is not None and context_cursor != self._context_cursor)):
                        return metadata()
                    self._condition.wait(min(self.poll_interval, remaining))
            finally:
                self._active -= 1
                self._condition.notify_all()

    def close(self):
        self._stop.set()
        with self._condition:
            self._condition.notify_all()
            thread = self._thread
        if thread is not None:
            thread.join()
