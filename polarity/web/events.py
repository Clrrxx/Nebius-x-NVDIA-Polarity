"""Thread-safe event bus feeding WebSocket clients.

Any thread (camera monitor, check worker, router cost hook) can ``publish``; each connected client has its own
asyncio queue on the server loop. Slow clients drop events instead of blocking the bench.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from typing import Any

from pydantic import BaseModel

log = logging.getLogger(__name__)


def _jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


class EventBus:
    def __init__(self, queue_size: int = 256) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subs: set[asyncio.Queue[str]] = set()
        self._lock = threading.Lock()
        self._queue_size = queue_size
        self.published = 0

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=self._queue_size)
        with self._lock:
            self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[str]) -> None:
        with self._lock:
            self._subs.discard(q)

    @staticmethod
    def _offer(q: asyncio.Queue[str], msg: str) -> None:
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            pass

    def publish(self, event_type: str, data: Any = None) -> None:
        """Send ``{"type", "data", "ts"}`` to every connected client (safe from any thread)."""
        self.published += 1
        loop = self._loop
        with self._lock:
            subs = list(self._subs)
        if loop is None or not subs or loop.is_closed():
            return
        msg = json.dumps({"type": event_type, "data": _jsonable(data), "ts": time.time()}, default=str)
        for q in subs:
            try:
                loop.call_soon_threadsafe(self._offer, q, msg)
            except RuntimeError:  # loop shutting down
                return
