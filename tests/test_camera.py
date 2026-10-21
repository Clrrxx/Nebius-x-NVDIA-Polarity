"""CameraService resilience (fake device): frames flow, a dropped device reconnects, the loop never crashes."""

from __future__ import annotations

import time

import numpy as np
import pytest

from polarity.edge import camera as camera_mod
from polarity.edge.camera import CameraService, DemoCameraSource


class FakeCap:
    def __init__(self, fail_after: int | None = None) -> None:
        self.reads = 0
        self.fail_after = fail_after
        self.released = False

    def read(self):  # noqa: ANN201
        self.reads += 1
        if self.fail_after is not None and self.reads > self.fail_after:
            return False, None
        img = np.full((72, 128, 3), (self.reads * 7) % 255, np.uint8)
        return True, img

    def get(self, prop: int) -> float:
        return 128.0

    def release(self) -> None:
        self.released = True


def _wait(pred, timeout: float = 5.0) -> bool:  # noqa: ANN001
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.02)
    return False


def test_reconnects_after_device_drops(monkeypatch: pytest.MonkeyPatch) -> None:
    caps = [FakeCap(fail_after=20), FakeCap()]
    opened: list[FakeCap] = []

    def fake_open(index: int, width: int, height: int):  # noqa: ANN202
        if not caps:
            return None, "no device"
        cap = caps.pop(0)
        opened.append(cap)
        return cap, None

    monkeypatch.setattr(camera_mod, "open_capture", fake_open)
    cam = CameraService(0, 1920, 1080, ring_hz=100)
    cam.start()
    try:
        assert _wait(lambda: cam.latest() is not None)
        assert _wait(lambda: len(opened) == 2 and cam.status()["connected"])  # dropped, then reconnected
        assert opened[0].released
        assert _wait(lambda: cam.sharpest_recent(1.0) is not None)
    finally:
        cam.stop()


def test_missing_camera_reports_status_without_crashing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(camera_mod, "open_capture", lambda *a: (None, "no backend could open the camera"))
    cam = CameraService(3, 640, 480)
    cam.start()
    try:
        assert _wait(lambda: cam.status()["error"] is not None)
        assert cam.latest() is None and cam.status()["connected"] is False
    finally:
        cam.stop()


def test_demo_source_prefers_team_photos(tmp_path, demo_set) -> None:  # noqa: ANN001
    import shutil

    root = tmp_path / "demo" / "lab1"
    shutil.copytree(demo_set, root)
    (root / "s3" / "correct.jpg").write_bytes((root / "s3" / "correct.png").read_bytes())
    src = DemoCameraSource(tmp_path / "demo", "lab1")
    src.start()
    assert src.scenes()[("s3", "correct")].suffix == ".jpg"
    assert src.set_scene("s3", "E_LED_REVERSED") and src.latest().label == "s3/E_LED_REVERSED"  # type: ignore[union-attr]
    assert not src.set_scene("s3", "nope")
