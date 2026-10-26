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


REAL_PHOTOS = Path(__file__).resolve().parents[1] / "data" / "real_photos" / "2026-10-21"
_BG = (60, 60, 60)


def _hand_placed_frame(cover: int | None = None) -> tuple[np.ndarray, dict[int, np.ndarray]]:
    """A portrait board between hand-placed markers like the team's first real rig: ids 0 and 1 upright along the
    top, 2 and 3 swapped and turned 90° along the bottom, with a red dot inside the board next to marker 0. Returns
    a 1920×1080 camera frame (mild keystone) and each marker's inner corner in frame coordinates."""
    m, q, w, h, pad = 110, 14, 200, 600, 60      # marker paper, white margin, inner gap, border around it all
    cw, ch = w + 2 * m + 2 * pad, h + 2 * m + 2 * pad
    canvas = np.full((ch, cw, 3), _BG, np.uint8)
    x0, y0 = pad + m, pad + m                    # top-left of the gap between the markers
    cv2.rectangle(canvas, (x0, y0), (x0 + w, y0 + h), (215, 215, 210), -1)
    cv2.circle(canvas, (x0 + 30, y0 + 30), 12, (30, 30, 220), -1)
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    spots = {0: ((x0 - m, y0 - m), 0, (x0 - q, y0 - q)), 1: ((x0 + w, y0 - m), 0, (x0 + w + q, y0 - q)),
             2: ((x0 - m, y0 + h), 1, (x0 - q, y0 + h + q)), 3: ((x0 + w, y0 + h), 1, (x0 + w + q, y0 + h + q))}
    for mid, ((mx, my), turns, _) in spots.items():
        if mid == cover:
            continue
        canvas[my : my + m, mx : mx + m] = 255
        tile = np.rot90(cv2.aruco.generateImageMarker(dictionary, mid, m - 2 * q), turns)
        canvas[my + q : my + m - q, mx + q : mx + m - q] = tile[..., None]
    src = np.array([[0, 0], [cw, 0], [cw, ch], [0, ch]], dtype=np.float32)
    dst = np.array([[720, 70], [720 + cw - 30, 80], [720 + cw + 25, 70 + ch], [705, 60 + ch]], dtype=np.float32)
    hmat = cv2.getPerspectiveTransform(src, dst)
    frame = cv2.warpPerspective(canvas, hmat, (1920, 1080), borderMode=cv2.BORDER_CONSTANT, borderValue=_BG)
    inner = {mid: cv2.perspectiveTransform(np.array([[c]], dtype=np.float32), hmat).reshape(2)
             for mid, (_, _, c) in spots.items()}
    return frame, inner


def _red_dot(img: np.ndarray) -> tuple[float, float]:
    """Centre of the red dot as fractions of the image width and height."""
    b, g, r = (img[..., k].astype(int) for k in range(3))
    ys, xs = np.nonzero((r > 150) & (g < 90) & (b < 90))
    return float(xs.mean()) / img.shape[1], float(ys.mean()) / img.shape[0]


def test_hand_placed_markers_any_order_turned_to_landscape() -> None:
    frame, inner = _hand_placed_frame()
    loc = BoardLocator()
    det = loc.detect(frame)
    assert det.found and det.markers_found == 4 and not det.inferred
    true_aspect = 628 / 228  # inner corners span (600 + 2·14) × (200 + 2·14)
    assert det.aspect is not None and abs(det.aspect - true_aspect) < 0.03 * true_aspect
    w, h = loc.warp_size(det)
    assert w == 1024 and abs(h - 1024 / true_aspect) <= 8
    # counter-clockwise turn: marker 1's inner corner becomes top-left and marker 0's bottom-left
    expected = np.stack([inner[1], inner[3], inner[2], inner[0]])
    assert np.abs(det.quad - expected).max() < 2.0
    warped = loc.warp(frame, det)
    assert warped is not None and warped.shape == (h, w, 3)
    x, y = _red_dot(warped)
    assert x < 0.15 and y > 0.75  # the dot next to marker 0 now sits bottom-left
    cw = BoardLocator(portrait_turn="cw").detect(frame)
    assert np.abs(cw.quad - np.stack([inner[2], inner[0], inner[1], inner[3]])).max() < 2.0


def test_hand_placed_markers_with_one_hidden() -> None:
    frame, inner = _hand_placed_frame()
    covered, _ = _hand_placed_frame(cover=3)
    expected = np.stack([inner[1], inner[3], inner[2], inner[0]])
    loc = BoardLocator()
    full = loc.detect(frame)
    learned = loc.detect(covered)  # same locator: the layout learned from the 4-marker frame
    assert learned.found and learned.inferred and learned.markers_found == 3
    assert learned.size == full.size
    assert np.abs(learned.quad - expected).max() < 3.0
    fresh = BoardLocator().detect(covered)  # never saw all four: completed from the marker squares alone
    assert fresh.found and fresh.inferred and "marker squares" in fresh.note
    assert np.abs(fresh.quad - expected).max() < 8.0  # single-marker extrapolation: a few px


def test_markers_that_do_not_outline_a_board_are_not_found() -> None:
    frame = np.full((1080, 1920, 3), _BG, np.uint8)
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    for k in range(4):  # four markers in a row
        x = 200 + k * 400
        frame[400:560, x : x + 160] = 255
        frame[420:540, x + 20 : x + 140] = cv2.aruco.generateImageMarker(dictionary, k, 120)[..., None]
    det = BoardLocator().detect(frame)
    assert det.markers_found == 4 and not det.found
    # The Board chip must agree with the locator: four markers seen, but no board to check.
    report = QualityGate(get_config().settings.quality).evaluate(frame, det.markers_found, 0.0, board_found=det.found)
    assert "markers" in report.failing and not chips(report)["board"]


def test_wrong_marker_ids_are_named_in_the_note() -> None:
    frame = np.full((1080, 1920, 3), _BG, np.uint8)
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    for k, mid in enumerate((10, 11, 12, 13)):  # right dictionary, wrong ids (someone else's printout)
        x = 200 + k * 400
        frame[400:560, x : x + 160] = 255
        frame[420:540, x + 20 : x + 140] = cv2.aruco.generateImageMarker(dictionary, mid, 120)[..., None]
    det = BoardLocator().detect(frame)
    assert not det.found and det.markers_found == 0
    assert "saw marker ids [10, 11, 12, 13]" in det.note and "[0, 1, 2, 3]" in det.note


@pytest.mark.parametrize(("name", "markers"), [("20261021_234020.jpg", 4), ("20261021_233534.jpg", 3)])
def test_real_photo_full_size_breadboard(name: str, markers: int) -> None:
    from polarity.cvio import imread

    frame = imread(REAL_PHOTOS / name)
    assert frame is not None, f"missing {REAL_PHOTOS / name}"
    loc = BoardLocator()
    det = loc.detect(frame)
    assert det.found and det.markers_found == markers and det.inferred == (markers == 3)
    assert det.aspect is not None and 2.6 < det.aspect < 3.4  # a full-size breadboard between the markers
    warped = loc.warp(frame, det)
    assert warped is not None and warped.shape[1] == 1024 and 300 <= warped.shape[0] <= 400


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


def test_locate_command_saves_top_down_views(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from polarity.cli import app

    result = CliRunner().invoke(app, ["locate", str(REAL_PHOTOS / "20261021_234020.jpg"), "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "20261021_234020_warped.jpg").exists()
    missing = CliRunner().invoke(app, ["locate", str(tmp_path / "nope.jpg"), "--out", str(tmp_path)])
    assert missing.exit_code == 1
