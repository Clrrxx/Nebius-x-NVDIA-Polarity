"""MotionMonitor: mean absolute difference of downscaled grey frames over a ~0.5 s window (0–255 scale)."""

from __future__ import annotations

import threading
from collections import deque

import cv2
import numpy as np


class MotionMonitor:
    def __init__(self, window_s: float = 0.5, size: tuple[int, int] = (160, 120)) -> None:
        self.window_s = window_s
        self.size = size
        self._history: deque[tuple[float, np.ndarray]] = deque(maxlen=64)
        self._value = 0.0
        self._lock = threading.Lock()

    def update(self, frame: np.ndarray, ts: float) -> float:
        """Add a frame (BGR or grey) taken at ``ts`` seconds; returns the current motion value."""
        gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, self.size, interpolation=cv2.INTER_AREA).astype(np.float32)
        with self._lock:
            self._history.append((ts, small))
            while len(self._history) > 2 and ts - self._history[1][0] >= self.window_s:
                self._history.popleft()
            ref_ts, ref = self._history[0]
            self._value = float(np.mean(np.abs(small - ref))) if ts - ref_ts > 0 else 0.0
            return self._value

    @property
    def value(self) -> float:
        with self._lock:
            return self._value

    def reset(self) -> None:
        with self._lock:
            self._history.clear()
            self._value = 0.0
