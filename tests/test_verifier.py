"""Check pipeline in mock mode: quality gate short-circuit, fix with hints, honesty paths, second look, LED."""

from __future__ import annotations

import pytest

from polarity.config import get_config
from polarity.engine.verifier import CheckRequest, Verifier
from polarity.llm.router import MemoryRecorder, ModelRouter
from polarity.models.lab import load_lab


@pytest.fixture
def setup():  # noqa: ANN201
    cfg = get_config()
    lab = load_lab(cfg.paths.labs / "lab1.yaml")
    rec = MemoryRecorder()
    return cfg, lab, Verifier(cfg, ModelRouter(cfg, recorder=rec)), rec


def _req(lab, step_id: str, frame, label: str, **kw) -> CheckRequest:  # noqa: ANN001
    return CheckRequest(lab=lab, step=lab.step(step_id), frame=frame, motion=0.0, mock_hint=label, **kw)


def test_quality_failure_makes_no_cloud_call(setup, scene) -> None:  # noqa: ANN001
    cfg, lab, verifier, rec = setup
    out = verifier.check(_req(lab, "s3", scene("s3", "_glare"), "_glare"))
    assert out.final.status == "uncertain" and out.final.reason.startswith("quality:")
    assert out.final.retake_instruction and not out.calls and not rec.calls


def test_markers_hidden_is_cant_tell(setup, scene) -> None:  # noqa: ANN001
    _, lab, verifier, rec = setup
    out = verifier.check(_req(lab, "s3", scene("s3", "_markers"), "_markers"))
    assert out.final.reason == "quality:markers" and "markers" in (out.final.retake_instruction or "")
    assert not rec.calls


def test_wrong_build_is_fix_with_hint_ladder(setup, scene) -> None:  # noqa: ANN001
    _, lab, verifier, _ = setup
    out = verifier.check(_req(lab, "s3", scene("s3", "E_LED_REVERSED"), "E_LED_REVERSED", hint_level=2))
    f = out.final
    assert f.status == "fix" and f.model_id == "MOCK"
    assert f.perception and "E_LED_REVERSED" in f.perception.detected_error_ids
    assert f.hint_text == lab.step("s3").error("E_LED_REVERSED").fix_hint_l2  # type: ignore[union-attr]
    assert out.warped is not None and out.warped.shape == (768, 1024, 3)


def test_hand_over_board_is_honest_cant_tell(setup, scene) -> None:  # noqa: ANN001
    _, lab, verifier, _ = setup
    out = verifier.check(_req(lab, "s3", scene("s3", "_hand"), "_hand"))
    assert out.final.status == "uncertain" and out.final.reason.startswith("model:not_visible")
    assert "hands" in (out.final.retake_instruction or "").lower()


def test_fine_detail_in_shadow_is_pass_partial(setup, scene) -> None:  # noqa: ANN001
    _, lab, verifier, _ = setup
    out = verifier.check(_req(lab, "s3", scene("s3", "_partial"), "_partial"))
    assert out.final.status == "pass_partial"
    assert out.final.double_check == [lab.step("s3").check("c_orientation").statement]  # type: ignore[union-attr]


def test_grey_zone_triggers_second_look(setup, scene) -> None:  # noqa: ANN001
    _, lab, verifier, _ = setup
    out = verifier.check(_req(lab, "s4", scene("s4", "correct"), "correct"))
    assert out.final.status == "pass" and out.final.second_look_used
    assert len([c for c in out.calls if c.role == "perception"]) == 2
    assert out.second_look_image is not None and out.second_look_image.shape == (768, 1024, 3)


def test_power_test_uses_physical_led_evidence(setup, scene) -> None:  # noqa: ANN001
    _, lab, verifier, _ = setup
    baseline = verifier.analyse(scene("s5", "correct"))[1]
    lit = verifier.check(_req(lab, "s6", scene("s6", "correct"), "correct", led_baseline=baseline))
    assert lit.final.status == "pass" and lit.final.reason == "led:lit" and lit.final.led["lit"] is True  # type: ignore[index]
    dark = verifier.check(_req(lab, "s6", scene("s6", "E_NO_LIGHT"), "correct", led_baseline=baseline))
    # Even if the (mock) model claimed the step looks right, the physical detector says the LED is off.
    assert dark.final.status == "fix" and dark.final.reason == "led:not_lit"


def test_typed_question_is_answered(setup, scene) -> None:  # noqa: ANN001
    _, lab, verifier, _ = setup
    out = verifier.check(_req(lab, "s3", scene("s3", "correct"), "correct", typed_question="Which leg is longer?"))
    assert out.final.status == "pass" and out.final.perception and out.final.perception.student_answer
