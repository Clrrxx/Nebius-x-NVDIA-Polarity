"""Runtime: builds and owns every long-lived service of a running bench or hub (database, media store, event bus,
model router, camera, verifier, session engine, edge monitor, lab registry)."""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from polarity.config import Config, get_config
from polarity.edge.camera import CameraService, DemoCameraSource, NullCameraSource
from polarity.edge.quality import chips
from polarity.engine.session_engine import SessionEngine
from polarity.engine.verifier import Verifier
from polarity.llm.router import ModelRouter
from polarity.models.lab import LabDefinition, dump_lab, list_labs, load_lab
from polarity.models.session import HelpRequest
from polarity.storage.db import Database
from polarity.storage.media import MediaStore
from polarity.web.events import EventBus

log = logging.getLogger(__name__)


class Labs:
    """Lab registry: published labs in ``labs/``, AI drafts in ``data/lab_drafts/``."""

    def __init__(self, labs_dir: Path, drafts_dir: Path) -> None:
        self.labs_dir = labs_dir
        self.drafts_dir = drafts_dir
        self._cache: dict[str, tuple[float, LabDefinition]] = {}

    def _path(self, lab_id: str) -> Path | None:
        for folder in (self.labs_dir, self.drafts_dir):
            path = folder / f"{lab_id}.yaml"
            if path.exists():
                return path
        return list_labs(self.labs_dir).get(lab_id) or list_labs(self.drafts_dir).get(lab_id)

    def get(self, lab_id: str) -> LabDefinition | None:
        path = self._path(lab_id)
        if path is None:
            return None
        mtime = path.stat().st_mtime
        cached = self._cache.get(lab_id)
        if cached and cached[0] == mtime:
            return cached[1]
        lab = load_lab(path)
        self._cache[lab_id] = (mtime, lab)
        return lab

    def list(self) -> list[dict[str, Any]]:
        out = []
        for source, folder in (("published", self.labs_dir), ("draft", self.drafts_dir)):
            for lab_id, path in list_labs(folder).items():
                lab = load_lab(path)
                out.append({"id": lab_id, "title": lab.title, "version": lab.version, "steps": len(lab.steps),
                            "ai_drafted": lab.ai_drafted, "source": source})
        return out

    def save(self, lab: LabDefinition, publish: bool) -> Path:
        if publish:
            lab = lab.model_copy(update={"ai_drafted": False})
            path = self.labs_dir / f"{lab.id}.yaml"
            draft = self.drafts_dir / f"{lab.id}.yaml"
            if draft.exists():
                draft.unlink()
        else:
            path = self.drafts_dir / f"{lab.id}.yaml"
        dump_lab(lab, path)
        self._cache.pop(lab.id, None)
        return path


class EdgeMonitor:
    """Analyses the latest frame at ``quality_hz`` and publishes the live quality chips over the WebSocket.
    Also caches the latest board detection for the MJPEG overlay and fills a pending LED baseline."""

    def __init__(self, rt: Runtime) -> None:
        self.rt = rt
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.detection: Any = None
        self.quality: Any = None
        self.camera_ok = False

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="edge-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def analyse_once(self) -> dict[str, Any]:
        cam = self.rt.camera
        frame = cam.latest()
        status = cam.status()
        if frame is None:
            payload = {"ok": False, "failing": ["camera"], "metrics": {}, "camera": status,
                       "chips": {"light": False, "focus": False, "glare": False, "board": False, "steady": False}}
            with self._lock:
                self.detection, self.quality, self.camera_ok = None, None, False
            return payload
        det, warped, quality = self.rt.verifier.analyse(frame.image, cam.motion.value)
        with self._lock:
            self.detection, self.quality, self.camera_ok = det, quality, True
        self.rt.engine.offer_baseline(warped, quality.ok)
        return {"ok": quality.ok, "failing": quality.failing,
                "metrics": {k: (round(v, 3) if isinstance(v, float) else v) for k, v in quality.metrics.items()},
                "chips": chips(quality), "camera": status, "inferred": bool(det.inferred)}

    def _run(self) -> None:
        period = 1.0 / max(0.5, float(self.rt.config.settings.camera.quality_hz))
        while not self._stop.is_set():
            t0 = time.monotonic()
            try:
                self.rt.bus.publish("quality", self.analyse_once())
            except Exception:  # noqa: BLE001 - monitoring must never take the server down
                log.exception("edge monitor error")
            self._stop.wait(max(0.05, period - (time.monotonic() - t0)))


def placeholder(text: str, width: int = 960, height: int = 540) -> np.ndarray:
    img = np.full((height, width, 3), (33, 24, 17), np.uint8)
    for i, line in enumerate(text.split("\n")):
        size = cv2.getTextSize(line, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)[0]
        cv2.putText(img, line, ((width - size[0]) // 2, height // 2 + i * 40), cv2.FONT_HERSHEY_SIMPLEX, 0.9,
                    (243, 237, 230), 2, cv2.LINE_AA)
    return img


class Runtime:
    def __init__(self, config: Config | None = None) -> None:
        self.config = config or get_config()
        p = self.config.paths
        self.db = Database(p.db)
        self.media = MediaStore(p.media)
        self.bus = EventBus()
        self.router = ModelRouter(self.config, recorder=self.db, on_cost=self._on_cost)
        env = self.config.env
        if self.config.role_override == "hub":
            self.camera: Any = NullCameraSource()
        elif env.camera_source == "demo":
            self.camera: Any = DemoCameraSource(p.demo, env.default_lab if (p.demo / env.default_lab).exists() else "lab1")
        else:
            cs = self.config.settings.camera
            self.camera = CameraService(env.camera_index, env.camera_width, env.camera_height, cs.ring_frames, cs.ring_hz)
        self.verifier = Verifier(self.config, self.router)
        self.labs = Labs(p.labs, p.drafts)
        self.engine = SessionEngine(self)
        self.monitor = EdgeMonitor(self)
        self.hub_client: Any = None
        self.started = False
        self.last_answer: dict[str, Any] | None = None

    def start(self) -> None:
        if self.started:
            return
        self.camera.start()
        self.monitor.start()
        if self.config.role_override == "bench" and self.config.hub_url and self.hub_client is None:
            from polarity.hub.client import HubClient

            self.hub_client = HubClient(self, self.config.hub_url)
            self.hub_client.start()
        self.started = True

    def stop(self) -> None:
        self.monitor.stop()
        self.camera.stop()
        if self.hub_client:
            self.hub_client.stop()
        self.started = False

    # ── hooks used by the engine ─────────────────────────────────────────────────────────────

    def _on_cost(self, session_usd: float, day_usd: float, session_id: str | None) -> None:
        self.bus.publish("cost_update", {"session_usd": round(session_usd, 4), "day_usd": round(day_usd, 4),
                                         "pricing_known": bool(self.config.prices)})

    def hub_send(self, kind: str, payload: dict[str, Any], thumb: np.ndarray | None = None) -> None:
        """Queue a record for the hub (bench role only; no-op otherwise)."""
        if self.hub_client is not None:
            self.hub_client.enqueue(kind, payload, thumb)

    def on_help_created(self, help_req: HelpRequest) -> None:
        """Called after a help request is stored: forward it to the hub and summarise it for the TA in the
        background with Nemotron Super (the bench never waits on this)."""
        self.hub_send("help", help_req.model_dump())
        if not help_req.is_simulated:
            from polarity.engine.diagnosis import diagnose_async

            diagnose_async(self, help_req)

    def help_payload(self, h: HelpRequest | None) -> dict[str, Any] | None:
        if h is None:
            return None
        session = self.db.get_session(h.session_id)
        lab = self.labs.get(session.lab_id) if session else None
        step = lab.step(h.step_id) if lab else None
        attempts = [a for a in self.db.list_attempts(h.session_id, h.step_id) if a.warped_image_path]
        return {"id": h.id, "session_id": h.session_id, "step_id": h.step_id, "step_title": step.title if step else h.step_id,
                "alias": session.student_alias if session else "?", "bench_id": session.bench_id if session else None,
                "trigger": h.trigger, "status": h.status, "created_at": h.created_at, "resolved_at": h.resolved_at,
                "summary": json.loads(h.summary_json) if h.summary_json else None, "is_simulated": h.is_simulated,
                "thumb": f"/media/{attempts[-1].warped_image_path}" if attempts else None}

    # ── frames for the UI ────────────────────────────────────────────────────────────────────

    def stream_frame(self, view: str = "raw", width: int = 960) -> bytes:
        """One JPEG for the MJPEG stream: the camera view with the board overlay, or the warped AI view."""
        frame = self.camera.latest()
        if frame is None:
            status = self.camera.status()
            img = placeholder("No camera picture\n" + (status.get("error") or "Waiting for the camera..."), width)
        else:
            det = self.monitor.detection
            if view == "warped":
                warped = self.verifier.locator.warp(frame.image, det) if det is not None and det.found else None
                img = warped if warped is not None else placeholder("Board not found\nShow all four corner markers",
                                                                    width, int(width * 0.75))
            else:
                img = self.verifier.locator.draw_overlay(frame.image, det) if det is not None else frame.image
            h, w = img.shape[:2]
            if w != width:
                img = cv2.resize(img, (width, int(h * width / w)), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return buf.tobytes() if ok else b""
