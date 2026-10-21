"""Edge CV: BoardLocator (ArUco + homography), QualityGate, MotionMonitor, LedDetector, marker mat."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from polarity.config import get_config
from polarity.demo.synthetic_board import inner_quad_in_frame
from polarity.edge.board import BoardLocator
from polarity.edge.led import LedDetector
from polarity.edge.markers import write_mat
from polarity.edge.motion import MotionMonitor
from polarity.edge.quality import QualityGate, chips, retake_for


@pytest.fixture
def locator() -> BoardLocator:
    return BoardLocator.from_config(get_config())


@pytest.fixture
def gate() -> QualityGate:
    return QualityGate(get_config().settings.quality)


def test_locator_warps_to_1024x768_and_matches_ground_truth(locator: BoardLocator, scene) -> None:  # noqa: ANN001
    frame = scene("s3", "correct")
    det = locator.detect(frame)
    assert det.found and det.markers_found == 4 and not det.inferred
    assert np.abs(det.quad - inner_quad_in_frame()).max() < 2.0
    warped = locator.warp(frame, det)
    assert warped is not None and warped.shape == (768, 1024, 3)


def test_three_markers_infer_fourth_corner(locator: BoardLocator, scene) -> None:  # noqa: ANN001
    frame = scene("s3", "correct")
    quad = inner_quad_in_frame()
    tr = quad[1].astype(int)
    cv2.rectangle(frame, (tr[0] - 5, tr[1] - 260), (tr[0] + 260, tr[1] + 5), (180, 180, 175), -1)  # hide marker 1
    det = locator.detect(frame)
    assert det.found and det.markers_found == 3 and det.inferred
    assert np.abs(det.quad[1] - quad[1]).max() < 3.0  # exact under perspective (12-corner homography)


def test_two_markers_is_not_found(locator: BoardLocator, scene) -> None:  # noqa: ANN001
    det = locator.detect(scene("s3", "_markers"))
    assert not det.found and det.markers_found == 2
    assert locator.warp(scene("s3", "_markers"), det) is None


def test_roi_mode_when_markers_disabled() -> None:
    loc = BoardLocator(markers_enabled=False, roi=(0.25, 0.25, 0.5, 0.5))
    frame = np.zeros((400, 800, 3), np.uint8)
    det = loc.detect(frame)
    assert det.found and det.mode == "roi"
    assert loc.warp(frame, det).shape == (768, 1024, 3)  # type: ignore[union-attr]


def test_zoom_crop_is_full_size(locator: BoardLocator, scene) -> None:  # noqa: ANN001
    frame = scene("s3", "correct")
    crop = locator.zoom_crop(frame, locator.detect(frame), (0.4, 0.4), 1.6)
    assert crop is not None and crop.shape == (768, 1024, 3)


@pytest.mark.parametrize(("label", "failing"), [("_dark", "dark"), ("_blur", "blur"), ("_glare", "glare")])
def test_quality_gate_flags_bad_images(locator: BoardLocator, gate: QualityGate, scene, label: str,  # noqa: ANN001
                                       failing: str) -> None:
    frame = scene("s3", label)
    det = locator.detect(frame)
    report = gate.evaluate(locator.warp(frame, det), det.markers_found, 0.0)
    assert not report.ok and failing in report.failing
    assert retake_for(report)


def test_quality_gate_passes_good_image(locator: BoardLocator, gate: QualityGate, scene) -> None:  # noqa: ANN001
    frame = scene("s3", "correct")
    det = locator.detect(frame)
    report = gate.evaluate(locator.warp(frame, det), det.markers_found, 0.0)
    assert report.ok, report
    assert all(chips(report).values())


def test_quality_gate_markers_and_motion(gate: QualityGate, locator: BoardLocator, scene) -> None:  # noqa: ANN001
    frame = scene("s3", "correct")
    det = locator.detect(frame)
    warped = locator.warp(frame, det)
    assert gate.evaluate(warped, 2, 0.0).failing == ["markers"]
    report = gate.evaluate(warped, 4, 20.0)
    assert report.failing == ["motion"] and not chips(report)["steady"]


def test_motion_monitor() -> None:
    mm = MotionMonitor(window_s=0.5)
    still = np.full((120, 160), 100, np.uint8)
    for i in range(10):
        mm.update(still, i * 0.1)
    assert mm.value < 0.5
    moved = still.copy()
    moved[:, :80] = 220
    assert mm.update(moved, 1.0) > 6.0


def _warp(locator: BoardLocator, frame: np.ndarray) -> np.ndarray:
    warped = locator.warp(frame, locator.detect(frame))
    assert warped is not None
    return warped


def test_led_detector_lit_vs_baseline(locator: BoardLocator, scene) -> None:  # noqa: ANN001
    led = LedDetector(get_config().settings.led)
    baseline = _warp(locator, scene("s5", "correct"))
    lit = led.detect(_warp(locator, scene("s6", "correct")), baseline)
    assert lit.lit and lit.signal_strength >= 0.6 and lit.blobs
    off = led.detect(_warp(locator, scene("s6", "E_NO_LIGHT")), baseline)  # finger on the button, LED dark
    assert not off.lit and off.signal_strength >= 0.6


def test_led_detector_synthetic_blob() -> None:
    led = LedDetector(get_config().settings.led)
    base = np.full((768, 1024, 3), (190, 195, 200), np.uint8)
    cur = base.copy()
    cv2.circle(cur, (500, 300), 18, (40, 40, 255), -1)   # saturated red (BGR)
    cv2.circle(cur, (500, 300), 6, (250, 250, 255), -1)  # over-exposed core
    res = led.detect(cur, base)
    assert res.lit and res.signal_strength >= 0.6
    assert abs(res.blobs[0]["cx"] - 500) < 3


def test_led_detector_is_cautious_without_baseline_or_when_covered(locator: BoardLocator, scene) -> None:  # noqa: ANN001
    led = LedDetector(get_config().settings.led)
    off = _warp(locator, scene("s6", "E_NO_LIGHT"))
    assert led.detect(off, None).signal_strength < 0.6
    baseline = _warp(locator, scene("s5", "correct"))
    covered = off.copy()
    det = led.detect(_warp(locator, scene("s6", "correct")), baseline)
    cx, cy = int(det.blobs[0]["cx"]), int(det.blobs[0]["cy"])
    cv2.circle(covered, (cx, cy), 32, (134, 166, 214), -1)  # a fingertip over the LED
    res = led.detect(covered, baseline)
    assert not res.lit and res.signal_strength < 0.6


def test_marker_mat_is_detectable(tmp_path: Path) -> None:
    pdf, png = write_mat(tmp_path)
    assert pdf.stat().st_size > 10_000 and png.exists()
    page = cv2.imread(str(png))
    small = cv2.resize(page, (page.shape[1] // 3, page.shape[0] // 3), interpolation=cv2.INTER_AREA)
    det = BoardLocator().detect(small)
    assert det.found and det.markers_found == 4 and sorted(det.ids) == [0, 1, 2, 3]
