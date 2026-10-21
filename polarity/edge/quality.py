"""QualityGate: decide on-device whether an image is good enough to send to the cloud at all.

Metrics on the warped (or ROI) grey image: variance of the Laplacian (focus), mean brightness, glare ratio
(pixels >= 250), markers found, and motion from MotionMonitor. A failing gate returns a local CAN'T TELL with a
specific retake instruction and makes no cloud call.
"""

from __future__ import annotations

import cv2
import numpy as np

from polarity.models.verdict import QualityReport

RETAKE_INSTRUCTIONS: dict[str, str] = {
    "dark": "It's too dark — switch on the ring light or move the lamp closer.",
    "bright": "It's too bright — move the lamp a little further away or dim the ring light.",
    "blur": "The picture is blurry — hold the board still for a second.",
    "glare": "There's glare — tilt the board slightly away from the light.",
    "markers": "I can't see all four corner markers — slide the board back inside them.",
    "motion": "Hands out of frame for a moment, then press Check.",
}

# Order matters: the first failing metric chooses the retake instruction shown to the student.
METRIC_ORDER = ("markers", "motion", "dark", "bright", "glare", "blur")

CHIP_NAMES = {"light": ("dark", "bright"), "focus": ("blur",), "glare": ("glare",), "board": ("markers",),
              "steady": ("motion",)}


def _gray(img: np.ndarray, width: int = 1024) -> np.ndarray:
    gray = img if img.ndim == 2 else cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape[:2]
    if w != width:
        gray = cv2.resize(gray, (width, max(1, int(round(h * width / w)))),
                          interpolation=cv2.INTER_AREA if w > width else cv2.INTER_LINEAR)
    return gray


def image_metrics(img: np.ndarray) -> dict[str, float]:
    """Focus, brightness and glare for an image (normalised to 1024 px wide)."""
    gray = _gray(img)
    return {
        "blur_var": float(cv2.Laplacian(gray, cv2.CV_64F).var()),
        "brightness": float(gray.mean()),
        "glare_ratio": float(np.count_nonzero(gray >= 250)) / float(gray.size),
    }


class QualityGate:
    def __init__(self, settings: object, markers_enabled: bool = True) -> None:
        self.s = settings
        self.markers_enabled = markers_enabled

    def evaluate(self, image: np.ndarray, markers_found: int | None = None,
                 motion: float | None = None) -> QualityReport:
        """Evaluate the warped board image (or the raw frame when the board was not found)."""
        s = self.s
        m = image_metrics(image)
        metrics: dict[str, float | int | None] = {**m, "markers": markers_found, "motion": motion}
        failing: list[str] = []
        if self.markers_enabled and markers_found is not None and markers_found < s.markers_min:  # type: ignore[attr-defined]
            failing.append("markers")
        if motion is not None and motion > s.motion_max:  # type: ignore[attr-defined]
            failing.append("motion")
        if m["brightness"] < s.brightness_min:  # type: ignore[attr-defined]
            failing.append("dark")
        elif m["brightness"] > s.brightness_max:  # type: ignore[attr-defined]
            failing.append("bright")
        if m["glare_ratio"] > s.glare_ratio_max:  # type: ignore[attr-defined]
            failing.append("glare")
        if m["blur_var"] < s.blur_var_min:  # type: ignore[attr-defined]
            failing.append("blur")
        failing.sort(key=METRIC_ORDER.index)
        return QualityReport(ok=not failing, metrics=metrics, failing=failing)


def chips(report: QualityReport) -> dict[str, bool]:
    """The five UI chips (Light, Focus, Glare, Board found, Steady) as pass/fail booleans."""
    return {chip: not any(f in report.failing for f in metrics) for chip, metrics in CHIP_NAMES.items()}


def retake_for(report: QualityReport) -> str | None:
    return RETAKE_INSTRUCTIONS.get(report.failing[0]) if report.failing else None
