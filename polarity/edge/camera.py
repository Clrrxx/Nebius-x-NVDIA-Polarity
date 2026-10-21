"""Camera sources.

``CameraService``: OpenCV capture on a background thread with the right backend per OS (Windows: DirectShow then
Media Foundation, with MJPG for 1080p30 on USB cams; macOS: AVFoundation; Linux: V4L2), configured resolution with
a 1280×720 fallback, auto-reconnect when the device drops, a ring buffer of recent frames scored for sharpness
(sampled at ``ring_hz`` so 15 frames ≈ 1 s), and motion tracking. A camera failure never raises into the server.

``DemoCameraSource``: plays demo scenes (``data/demo/<lab>/<step>/<label>``) so the whole flow runs with no
hardware. Team photos (``.jpg``) override synthetic renders (``.png``).
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from polarity.cvio import imread
from polarity.edge.motion import MotionMonitor

log = logging.getLogger(__name__)

IMAGE_EXT = (".jpg", ".jpeg", ".png", ".bmp", ".webp")


@dataclass
class Frame:
    image: np.ndarray
    ts: float
    sharpness: float = 0.0
    label: str | None = None  # demo scene "s3/E_LED_REVERSED"; None for a real camera


def sharpness_score(img: np.ndarray) -> float:
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img
    small = cv2.resize(gray, (480, max(1, int(gray.shape[0] * 480 / gray.shape[1]))), interpolation=cv2.INTER_AREA)
    return float(cv2.Laplacian(small, cv2.CV_64F).var())


def backend_order() -> list[int]:
    if sys.platform == "win32":
        return [cv2.CAP_DSHOW, cv2.CAP_MSMF]
    if sys.platform == "darwin":
        return [cv2.CAP_AVFOUNDATION]
    return [cv2.CAP_V4L2, cv2.CAP_ANY]


def open_capture(index: int, width: int, height: int) -> tuple[Any, str | None]:
    """Open camera ``index`` with the OS backends in order. Returns ``(cap, error)``."""
    last_error = "no backend could open the camera"
    for backend in backend_order():
        cap = cv2.VideoCapture(index, backend)
        if not cap.isOpened():
            cap.release()
            continue
        if sys.platform == "win32":
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, 30)
        ok, frame = cap.read()
        if not ok or frame is None:  # requested mode unsupported: fall back to 1280×720
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            ok, frame = cap.read()
        if ok and frame is not None:
            return cap, None
        cap.release()
        last_error = "camera opened but returned no frames"
    return None, last_error


def probe_devices(max_index: int = 5) -> list[dict[str, Any]]:
    """Try camera indices 0..max_index and report which open and at what resolution."""
    found = []
    for idx in range(max_index + 1):
        cap, err = open_capture(idx, 1920, 1080)
        if cap is None:
            found.append({"index": idx, "ok": False, "error": err})
            continue
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        found.append({"index": idx, "ok": True, "resolution": f"{w}x{h}"})
        cap.release()
    return found


class CameraService:
    """Background OpenCV capture with ring buffer, motion tracking and auto-reconnect."""

    source_name = "opencv"

    def __init__(self, index: int, width: int, height: int, ring_frames: int = 15, ring_hz: float = 15.0,
                 motion: MotionMonitor | None = None) -> None:
        self.index, self.width, self.height = index, width, height
        self._ring: deque[Frame] = deque(maxlen=ring_frames)
        self._ring_period = 1.0 / max(1.0, ring_hz)
        self.motion = motion or MotionMonitor()
        self._latest: Frame | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._connected = False
        self._error: str | None = None
        self._resolution: tuple[int, int] | None = None
        self._fps = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="camera", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)

    def _run(self) -> None:
        cap = None
        failures = 0
        last_ring = 0.0
        frames, t_count = 0, time.monotonic()
        while not self._stop.is_set():
            try:
                if cap is None:
                    cap, err = open_capture(self.index, self.width, self.height)
                    if cap is None:
                        self._set_status(False, err)
                        self._stop.wait(1.5)
                        continue
                    self._resolution = (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
                    self._set_status(True, None)
                    failures = 0
                ok, img = cap.read()
                if not ok or img is None:
                    failures += 1
                    if failures >= 15:  # device unplugged or asleep: release and reconnect
                        cap.release()
                        cap = None
                        self._set_status(False, "camera disconnected; reconnecting")
                    else:
                        time.sleep(0.03)
                    continue
                failures = 0
                now = time.monotonic()
                frame = Frame(image=img, ts=now)
                with self._lock:
                    self._latest = frame
                frames += 1
                if now - t_count >= 2.0:
                    self._fps = frames / (now - t_count)
                    frames, t_count = 0, now
                if now - last_ring >= self._ring_period:
                    frame.sharpness = sharpness_score(img)
                    self.motion.update(img, now)
                    with self._lock:
                        self._ring.append(frame)
                    last_ring = now
            except Exception as exc:  # noqa: BLE001 - the camera loop must never crash the server
                log.exception("camera loop error")
                self._set_status(False, f"camera error: {exc}")
                if cap is not None:
                    cap.release()
                cap = None
                self._stop.wait(1.0)
        if cap is not None:
            cap.release()

    def _set_status(self, connected: bool, error: str | None) -> None:
        with self._lock:
            self._connected = connected
            self._error = error
            if not connected:
                self._latest = None
                self._ring.clear()

    def latest(self) -> Frame | None:
        with self._lock:
            return self._latest

    def sharpest_recent(self, seconds: float = 1.0) -> Frame | None:
        """Sharpest frame from the last ``seconds`` (falls back to the latest frame)."""
        now = time.monotonic()
        with self._lock:
            recent = [f for f in self._ring if now - f.ts <= seconds]
            latest = self._latest
        if recent:
            return max(recent, key=lambda f: f.sharpness)
        return latest

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {"source": self.source_name, "index": self.index, "connected": self._connected,
                    "error": self._error, "resolution": list(self._resolution) if self._resolution else None,
                    "fps": round(self._fps, 1)}


class DemoCameraSource:
    """Plays demo scenes as if they were camera frames (CAMERA_SOURCE=demo)."""

    source_name = "demo"

    def __init__(self, demo_dir: Path, lab_id: str = "lab1") -> None:
        self.root = demo_dir / lab_id
        self.lab_id = lab_id
        self.motion = MotionMonitor()
        self._lock = threading.Lock()
        self._scene: tuple[str, str] = ("s1", "_empty")
        self._cache: dict[tuple[str, str], np.ndarray] = {}

    def start(self) -> None:
        if not self.scenes():
            from polarity.demo.synthetic_board import render_all

            log.info("No demo scenes found; rendering the synthetic set into %s (one-time, ~10 s)", self.root)
            render_all(self.root)
        if self._scene not in self.scenes():
            first = next(iter(self.scenes()), None)
            if first:
                self._scene = first

    def stop(self) -> None:
        pass

    def scenes(self) -> dict[tuple[str, str], Path]:
        """(step, label) → image path, preferring team photos over synthetic renders."""
        out: dict[tuple[str, str], Path] = {}
        if not self.root.exists():
            return out
        for step_dir in sorted(p for p in self.root.iterdir() if p.is_dir()):
            for img in sorted(step_dir.iterdir()):
                if img.suffix.lower() not in IMAGE_EXT:
                    continue
                key = (step_dir.name, img.stem)
                if key not in out or img.suffix.lower() != ".png":
                    out[key] = img
        return out

    def set_scene(self, step: str, label: str) -> bool:
        if (step, label) not in self.scenes():
            return False
        with self._lock:
            self._scene = (step, label)
        return True

    @property
    def scene(self) -> tuple[str, str]:
        with self._lock:
            return self._scene

    def _image(self, key: tuple[str, str]) -> np.ndarray | None:
        if key not in self._cache:
            path = self.scenes().get(key)
            img = imread(path) if path else None
            if img is None:
                return None
            self._cache[key] = img
        return self._cache[key]

    def latest(self) -> Frame | None:
        key = self.scene
        img = self._image(key)
        if img is None:
            return None
        return Frame(image=img, ts=time.monotonic(), sharpness=0.0, label=f"{key[0]}/{key[1]}")

    def sharpest_recent(self, seconds: float = 1.0) -> Frame | None:
        return self.latest()

    def status(self) -> dict[str, Any]:
        step, label = self.scene
        img = self._image((step, label))
        return {"source": self.source_name, "index": None, "connected": img is not None, "error": None,
                "resolution": [img.shape[1], img.shape[0]] if img is not None else None, "fps": None,
                "scene": {"step": step, "label": label}}


class NullCameraSource:
    """No camera (hub role: the TA laptop only aggregates benches)."""

    source_name = "none"

    def __init__(self) -> None:
        self.motion = MotionMonitor()

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def latest(self) -> Frame | None:
        return None

    def sharpest_recent(self, seconds: float = 1.0) -> Frame | None:
        return None

    def status(self) -> dict[str, Any]:
        return {"source": "none", "index": None, "connected": False, "error": "hub mode: no camera", "resolution": None,
                "fps": None}
