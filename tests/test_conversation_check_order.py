"""Controlled check-completion interleavings, not outage frequency estimates."""
import sqlite3
import threading

import pytest

from avatar.conversation_changes import ConversationChanges


@pytest.mark.parametrize('old_fails', [False, True])
def test_success_started_before_observed_failure_cannot_clear_error_without_fresh_read(monkeypatch, old_fails):
    watch = ConversationChanges(':memory:', 'instance')
    entered, release = threading.Event(), threading.Event()
    def read():
        if threading.current_thread() is worker:
            entered.set(); release.wait()
            if old_fails: raise sqlite3.DatabaseError('controlled older failure')
            return 0
        if old_fails: return 0
        raise sqlite3.DatabaseError('controlled newer failure')
    monkeypatch.setattr(watch, '_read_revision', read)
    worker = threading.Thread(target=watch.check)
    try:
        worker.start(); assert entered.wait(2)
        watch.check()
        if not old_fails: assert watch._error
        release.set(); worker.join(2); assert not worker.is_alive()
        # Either completion order must remain unavailable until a check that
        # actually starts after the observed failure succeeds.
        assert watch._error
        monkeypatch.setattr(watch, '_read_revision', lambda: 0)
        watch.check(); assert not watch._error
    finally:
        release.set(); worker.join(2); watch.close()
