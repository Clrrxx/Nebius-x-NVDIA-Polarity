"""Rig tools that open an OpenCV window on the bench computer.

``polarity capture``: live preview + quality chips; Space saves raw + warped photos into
``data/eval/<lab>/<step>/<label>/`` for the evaluation dataset (real camera only: synthetic demo frames must never
enter the eval set). ``polarity calibrate``: live metrics, LED mask and threshold sliders; on quit it prints a
YAML block to paste into ``config/settings.yaml``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from polarity.cvio import imwrite
from polarity.edge.quality import CHIP_NAMES, chips

WINDOW_SIZE = (1280, 720)
GREEN, AMBER, WHITE, MUTED = (94, 197, 34), (11, 158, 245), (243, 237, 230), (169, 152, 139)


class RigToolError(Exception):
    pass


def valid_labels(lab: Any, step_id: str) -> list[str]:
    step = lab.step(step_id)
    if step is None:
        raise RigToolError(f"Unknown step {step_id!r}; steps: {', '.join(s.id for s in lab.steps)}")
    labels = ["correct", *[e.id for e in step.common_errors]]
    if step.led_check is not None:
        labels.append("_baseline")
    return labels


def next_index(folder: Path) -> int:
    nums = [int(m.group(1)) for p in folder.glob("*_raw.*") if (m := re.match(r"(\d+)_raw", p.stem))]
    return max(nums, default=0) + 1


def save_capture(raw: np.ndarray, warped: np.ndarray | None, folder: Path) -> tuple[Path, Path | None]:
    """Save ``NNNN_raw.jpg`` (+ ``NNNN_warped.jpg`` when the board was found)."""
    folder.mkdir(parents=True, exist_ok=True)
    n = next_index(folder)
    raw_path = folder / f"{n:04d}_raw.jpg"
    imwrite(raw_path, raw, [cv2.IMWRITE_JPEG_QUALITY, 95])
    warped_path = None
    if warped is not None:
        warped_path = folder / f"{n:04d}_warped.jpg"
        imwrite(warped_path, warped, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return raw_path, warped_path


def _fit(img: np.ndarray, w: int, h: int) -> np.ndarray:
    ih, iw = img.shape[:2]
    scale = min(w / iw, h / ih)
    resized = cv2.resize(img, (max(1, int(iw * scale)), max(1, int(ih * scale))), interpolation=cv2.INTER_AREA)
    canvas = np.full((h, w, 3), (20, 16, 12), np.uint8)
    y, x = (h - resized.shape[0]) // 2, (w - resized.shape[1]) // 2
    canvas[y : y + resized.shape[0], x : x + resized.shape[1]] = resized
    return canvas


def compose_view(frame: np.ndarray, overlay: np.ndarray, warped: np.ndarray | None, quality: Any,
                 lines: list[str], side_bottom: np.ndarray | None = None) -> np.ndarray:
    """1280×720 window: camera (left), warped view + optional second panel and status text (right)."""
    w, h = WINDOW_SIZE
    canvas = np.full((h, w, 3), (20, 16, 12), np.uint8)
    canvas[:, :840] = _fit(overlay, 840, h)
    canvas[0:315, 860:1280] = _fit(warped, 420, 315) if warped is not None else _fit(
        np.full((315, 420, 3), 40, np.uint8), 420, 315)
    if warped is None:
        cv2.putText(canvas, "Board not found", (930, 165), cv2.FONT_HERSHEY_SIMPLEX, 0.8, AMBER, 2, cv2.LINE_AA)
    y = 340
    if side_bottom is not None:
        canvas[325:575, 860:1280] = _fit(side_bottom, 420, 250)
        y = 600
    for name, ok in chips(quality).items():
        label = {"light": "Light", "focus": "Focus", "glare": "Glare", "board": "Board", "steady": "Steady"}[name]
        if side_bottom is None:
            cv2.putText(canvas, f"{label}: {'OK' if ok else 'CHECK'}", (870, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                        GREEN if ok else AMBER, 2, cv2.LINE_AA)
            y += 28
    for line in lines:
        if y > h - 10:
            break
        cv2.putText(canvas, line, (870, y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, WHITE, 1, cv2.LINE_AA)
        y += 22
    return canvas


def _metrics_line(quality: Any) -> str:
    m = quality.metrics
    return (f"focus {m.get('blur_var', 0):.0f} | light {m.get('brightness', 0):.0f} | glare {m.get('glare_ratio', 0):.3f}"
            f" | markers {m.get('markers')} | motion {m.get('motion') or 0:.1f}")


def _gui_available() -> bool:
    try:
        cv2.namedWindow("polarity-probe", cv2.WINDOW_NORMAL)
        cv2.destroyWindow("polarity-probe")
        return True
    except cv2.error:
        return False


def run_capture(config: Any, lab: Any, step_id: str, label: str, camera: Any, verifier: Any) -> int:
    if getattr(camera, "source_name", "") == "demo":
        raise RigToolError("Capture records real photos for the evaluation set; CAMERA_SOURCE=demo is not allowed.")
    labels = valid_labels(lab, step_id)
    if label not in labels:
        raise RigToolError(f"Unknown label {label!r} for {step_id}; use one of: {', '.join(labels)}")
    if not _gui_available():
        raise RigToolError("OpenCV has no GUI here. Install opencv-contrib-python (not the -headless build).")
    folder = config.paths.eval / lab.id / step_id / label
    saved = next_index(folder) - 1
    title = "Polarity capture"
    cv2.namedWindow(title, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(title, *WINDOW_SIZE)
    last = ""
    camera.start()
    try:
        while True:
            frame = camera.latest()
            if frame is None:
                img = np.full((WINDOW_SIZE[1], WINDOW_SIZE[0], 3), 20, np.uint8)
                cv2.putText(img, "Waiting for the camera...", (420, 360), cv2.FONT_HERSHEY_SIMPLEX, 1, WHITE, 2)
                cv2.imshow(title, img)
            else:
                det, warped, quality = verifier.analyse(frame.image, camera.motion.value)
                overlay = verifier.locator.draw_overlay(frame.image, det)
                lines = [f"{lab.id} / {step_id} / {label}", f"saved so far: {saved}", _metrics_line(quality),
                         "SPACE save   Q quit", last]
                cv2.imshow(title, compose_view(frame.image, overlay, warped, quality, lines))
            key = cv2.waitKey(30) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == 32 and frame is not None:
                raw_path, _ = save_capture(frame.image, warped, folder)
                saved += 1
                failing = ", ".join(quality.failing)
                last = f"saved {raw_path.name}" + (f" (quality: {failing})" if failing else "")
    finally:
        camera.stop()
        cv2.destroyAllWindows()
    return saved


CAL_SLIDERS = [  # (section, key, trackbar max, scale)
    ("quality", "blur_var_min", 400, 1.0),
    ("quality", "brightness_min", 255, 1.0),
    ("quality", "brightness_max", 255, 1.0),
    ("quality", "glare_ratio_max", 100, 0.001),
    ("quality", "motion_max", 400, 0.1),
    ("led", "v_delta_min", 150, 1.0),
    ("led", "s_min", 255, 1.0),
    ("led", "min_area_px", 400, 1.0),
]


def calibration_yaml(settings: Any) -> str:
    q, led = settings.quality, settings.led
    return "\n".join([
        "quality:",
        f"  blur_var_min: {q.blur_var_min:g}",
        f"  brightness_min: {q.brightness_min:g}",
        f"  brightness_max: {q.brightness_max:g}",
        f"  glare_ratio_max: {q.glare_ratio_max:g}",
        f"  markers_min: {q.markers_min}",
        f"  motion_max: {q.motion_max:g}",
        "led:",
        f"  v_delta_min: {led.v_delta_min:g}",
        f"  s_min: {led.s_min}",
        f"  min_area_px: {led.min_area_px}",
    ])


def run_calibrate(config: Any, camera: Any, verifier: Any) -> str:
    if not _gui_available():
        raise RigToolError("OpenCV has no GUI here. Install opencv-contrib-python (not the -headless build).")
    title = "Polarity calibrate"
    cv2.namedWindow(title, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(title, *WINDOW_SIZE)
    s = config.settings

    def setter(section: str, key: str, scale: float) -> Any:
        def _set(pos: int) -> None:
            target = getattr(s, section)
            current = getattr(target, key)
            setattr(target, key, type(current)(pos * scale))
        return _set

    for section, key, maximum, scale in CAL_SLIDERS:
        value = getattr(getattr(s, section), key)
        cv2.createTrackbar(f"{section}.{key}", title, int(round(value / scale)), maximum, setter(section, key, scale))
    baseline = None
    camera.start()
    try:
        while True:
            frame = camera.latest()
            key = cv2.waitKey(30) & 0xFF
            if key in (ord("q"), 27):
                break
            if frame is None:
                continue
            det, warped, quality = verifier.analyse(frame.image, camera.motion.value)
            if key == ord("b") and warped is not None:
                baseline = warped.copy()
            mask_view = None
            led_line = "LED: press B with the LED off to store a baseline"
            if warped is not None:
                mask = verifier.led.mask(warped, baseline)
                mask_view = warped.copy()
                mask_view[mask > 0] = (191, 212, 45)
                res = verifier.led.detect(warped, baseline)
                led_line = f"LED: {'lit' if res.lit else 'dark'} (strength {res.signal_strength:.2f})"
            failing = [f for names in CHIP_NAMES.values() for f in names if f in quality.failing]
            lines = [_metrics_line(quality), led_line, f"failing: {', '.join(failing) or 'none'}",
                     "B baseline   Q quit (prints settings)"]
            overlay = verifier.locator.draw_overlay(frame.image, det)
            cv2.imshow(title, compose_view(frame.image, overlay, warped, quality, lines, side_bottom=mask_view))
    finally:
        camera.stop()
        cv2.destroyAllWindows()
    return calibration_yaml(s)
