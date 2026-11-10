"""Cooperative cancellation with thread-safe async transport interruption."""
from __future__ import annotations

import asyncio
import threading


class Cancelled(Exception):
    """The caller explicitly stopped this operation."""


class CancellationToken:
    def __init__(self):
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._callbacks = set()

    @property
    def cancelled(self):
        return self._event.is_set()

    def checkpoint(self):
        if self.cancelled:
            raise Cancelled("operation cancelled")

    def cancel(self):
        with self._lock:
            self._event.set()
            callbacks = tuple(self._callbacks)
            self._callbacks.clear()
        for callback in callbacks:
            callback()

    def subscribe(self, callback):
        with self._lock:
            cancelled = self.cancelled
            if not cancelled:
                self._callbacks.add(callback)
        if cancelled:
            callback()
        def remove():
            with self._lock:
                self._callbacks.discard(callback)
        return remove

    def run_async(self, factory, *, timeout=None):
        async def run():
            self.checkpoint()
            loop, task = asyncio.get_running_loop(), asyncio.current_task()
            def interrupt():
                try:
                    loop.call_soon_threadsafe(task.cancel)
                except RuntimeError:
                    pass  # The operation has already closed its event loop.
            unsubscribe = self.subscribe(interrupt)
            try:
                if timeout is None:
                    return await factory()
                return await asyncio.wait_for(factory(), timeout=timeout)
            except asyncio.CancelledError:
                raise Cancelled("operation cancelled") from None
            except asyncio.TimeoutError:
                # Python 3.10's asyncio timeout is not the built-in alias yet.
                raise TimeoutError('operation deadline exceeded') from None
            finally:
                unsubscribe()
        return asyncio.run(run())
