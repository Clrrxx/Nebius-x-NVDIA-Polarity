"""Rig tools: label validation, capture file naming, composed window, calibration output, demo refusal."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from typer.testing import CliRunner

from polarity.cli import app
from polarity.config import get_config
from polarity.edge.rigtools import (
    RigToolError,
    calibration_yaml,
    compose_view,
    next_index,
    run_capture,
    save_capture,
    valid_labels,
)
from polarity.models.lab import load_lab
from polarity.models.verdict import QualityReport


@pytest.fixture
def lab():  # noqa: ANN201
    return load_lab(get_config().paths.labs / "lab1.yaml")


def test_valid_labels(lab) -> None:  # noqa: ANN001
    assert valid_labels(lab, "s3") == ["correct", "E_LED_REVERSED", "E_LED_SAME_STRIP", "E_LED_NOT_CONNECTED"]
    assert "_baseline" in valid_labels(lab, "s6")
    with pytest.raises(RigToolError):
        valid_labels(lab, "s9")


def test_save_capture_numbers_files(tmp_path: Path) -> None:
    raw = np.zeros((120, 160, 3), np.uint8)
    folder = tmp_path / "eval" / "lab1" / "s3" / "E_LED_REVERSED"
    assert next_index(folder) == 1
    r1, w1 = save_capture(raw, raw, folder)
    r2, w2 = save_capture(raw, None, folder)
    assert (r1.name, w1.name if w1 else None) == ("0001_raw.jpg", "0001_warped.jpg")
    assert (r2.name, w2) == ("0002_raw.jpg", None)
    assert next_index(folder) == 3


def test_compose_view_shapes() -> None:
    frame = np.zeros((1080, 1920, 3), np.uint8)
    q = QualityReport(ok=False, metrics={"blur_var": 10.0, "brightness": 40.0, "glare_ratio": 0.0, "markers": 2,
                                         "motion": 0.0}, failing=["markers", "dark"])
    assert compose_view(frame, frame, None, q, ["hello"]).shape == (720, 1280, 3)
    warped = np.zeros((768, 1024, 3), np.uint8)
    assert compose_view(frame, frame, warped, q, ["a", "b", "c", "d"], side_bottom=warped).shape == (720, 1280, 3)


def test_calibration_yaml_lists_tuned_keys() -> None:
    text = calibration_yaml(get_config().settings)
    for key in ("blur_var_min", "brightness_max", "glare_ratio_max", "v_delta_min", "min_area_px"):
        assert key in text


def test_capture_refuses_demo_camera(lab) -> None:  # noqa: ANN001
    class Demo:
        source_name = "demo"

    with pytest.raises(RigToolError, match="demo"):
        run_capture(get_config(), lab, "s3", "correct", Demo(), None)
    result = CliRunner().invoke(app, ["capture", "--step", "s3", "--label", "correct"])
    assert result.exit_code == 2 and "real camera" in result.output
