"""Bench → hub sync (BUILD_PROMPT.md 13.4, P1).

Run the TA laptop with ``polarity run --role hub --lan`` and each bench with
``polarity run --role bench --hub-url http://<hub-ip>:8765 --bench-id B07``. Benches queue sessions, attempts and
help requests in a persistent outbox (SQLite) and a background thread posts them to the hub, retrying while the hub
is unreachable. Board thumbnails are NOT sent unless ``hub.send_thumbnails: true`` (privacy default). Requests carry
the TA PIN as ``X-TA-PIN``, so benches and hub must share the same PIN.
"""

from __future__ import annotations

import base64
import logging
import threading
from collections.abc import Callable
from typing import Any

import cv2
import numpy as np

log = logging.getLogger(__name__)

PostFn = Callable[[str, dict[str, Any], dict[str, str]], int]


def http_post(url: str, body: dict[str, Any], headers: dict[str, str]) -> int:
    import httpx

    return httpx.post(url, json=body, headers=headers, timeout=5.0).status_code


class HubClient:
    def __init__(self, rt: Any, hub_url: str, post: PostFn | None = None) -> None:
        self.rt = rt
        self.url = hub_url.rstrip("/") + "/api/hub/ingest"
        self._post = post or http_post
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_error: str | None = None
        self.sent = 0

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="hub-sync", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=3)

    def enqueue(self, kind: str, payload: dict[str, Any], thumb: np.ndarray | None = None) -> None:
        body: dict[str, Any] = {"kind": kind, "bench_id": self.rt.config.bench_id, "payload": payload}
        if thumb is not None and self.rt.config.settings.hub.send_thumbnails:
            h, w = thumb.shape[:2]
            small = cv2.resize(thumb, (320, int(h * 320 / w)), interpolation=cv2.INTER_AREA)
            ok, buf = cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ok:
                body["thumb_b64"] = base64.b64encode(buf.tobytes()).decode("ascii")
        self.rt.db.outbox_add(kind, body)
        self._wake.set()

    def flush(self) -> int:
        """Send queued records in order; stop at the first failure (the hub is probably unreachable)."""
        import json

        pin = self.rt.config.env.ta_pin.get_secret_value()
        delivered = 0
        for item in self.rt.db.outbox_pending():
            try:
                status = self._post(self.url, json.loads(item["payload_json"]), {"X-TA-PIN": pin})
            except Exception as exc:  # noqa: BLE001 - network errors just keep the item queued
                self.last_error = f"{type(exc).__name__}: {exc}"
                self.rt.db.outbox_failed(item["id"], self.last_error)
                break
            if 200 <= status < 300:
                self.rt.db.outbox_done(item["id"])
                delivered += 1
                self.sent += 1
                self.last_error = None
            else:
                self.last_error = f"hub answered HTTP {status}"
                self.rt.db.outbox_failed(item["id"], self.last_error)
                break
        return delivered

    def pending(self) -> int:
        return len(self.rt.db.outbox_pending(500))

    def _run(self) -> None:
        retry = float(self.rt.config.settings.hub.retry_seconds)
        while not self._stop.is_set():
            self._wake.wait(retry)
            self._wake.clear()
            if self._stop.is_set():
                break
            try:
                self.flush()
            except Exception:  # noqa: BLE001 - sync must never break the bench
                log.exception("hub sync failed")
