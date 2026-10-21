"""Deterministic decision policy (BUILD_PROMPT.md 9.4): table-driven cases plus the second-look combiner."""

from __future__ import annotations

from typing import Any

import pytest

from polarity.engine.decision import Decision, combine_second_look, decide, needs_second_look
from polarity.models.lab import Check, CommonError, LedCheck, Step
from polarity.models.verdict import CheckResult, LedResult, PerceptionVerdict, QualityReport

ERR = CommonError(id="E_X", description="d", visual_cue="v", fix_hint_l1="1", fix_hint_l2="2", fix_hint_l3="3",
                  related_checks=["c_a"])
STEP = Step(id="s3", title="LED", instruction="i", checks=[
    Check(id="c_a", statement="a"), Check(id="c_b", statement="b"),
    Check(id="c_fine", statement="fine detail", allow_uncertain=True),
    Check(id="c_opt", statement="optional", required=False)], common_errors=[ERR])
LED_STEP = Step(id="s6", title="Power", instruction="i", checks=[Check(id="c_led_lit", statement="lit")],
                led_check=LedCheck(expect_lit=True, instruction_for_capture="hold"))


def v(results: dict[str, str], conf: float = 0.9, errors: list[str] | None = None, step_id: str = "s3",
      retake: str | None = None) -> PerceptionVerdict:
    return PerceptionVerdict(step_id=step_id, checks=[CheckResult(id=k, result=r, observation="o")  # type: ignore[arg-type]
                                                      for k, r in results.items()],
                             detected_error_ids=errors or [], confidence=conf, spoken_feedback="s",
                             retake_instruction=retake)


ALL_PASS = {"c_a": "pass", "c_b": "pass", "c_fine": "pass", "c_opt": "pass"}

CASES: list[tuple[str, dict[str, Any], str, str]] = [
    ("all pass, confident", {"verdict": v(ALL_PASS)}, "pass", "model:pass"),
    ("all pass, conf exactly pass_min", {"verdict": v(ALL_PASS, 0.75)}, "pass", "model:pass"),
    ("all pass, low confidence", {"verdict": v(ALL_PASS, 0.6)}, "uncertain", "model:low_confidence"),
    ("one fail, confident", {"verdict": v({**ALL_PASS, "c_a": "fail"}, 0.8, ["E_X"])}, "fix", "model:fail c_a"),
    ("fail at exactly fix_min", {"verdict": v({**ALL_PASS, "c_b": "fail"}, 0.6)}, "fix", "model:fail c_b"),
    ("fail below fix_min", {"verdict": v({**ALL_PASS, "c_a": "fail"}, 0.5)}, "uncertain", "model:low_confidence_fail"),
    ("optional check fails", {"verdict": v({**ALL_PASS, "c_opt": "fail"}, 0.9)}, "fix", "model:fail c_opt"),
    ("fine detail not visible → partial", {"verdict": v({**ALL_PASS, "c_fine": "not_visible"})}, "pass_partial",
     "model:pass_partial"),
    ("fine detail missing from output → partial", {"verdict": v({"c_a": "pass", "c_b": "pass"})}, "pass_partial",
     "model:pass_partial"),
    ("required check not visible", {"verdict": v({**ALL_PASS, "c_b": "not_visible"})}, "uncertain",
     "model:not_visible c_b"),
    ("required check missing from output", {"verdict": v({"c_a": "pass", "c_fine": "pass"})}, "uncertain",
     "model:not_visible c_b"),
    ("partial but low confidence", {"verdict": v({**ALL_PASS, "c_fine": "not_visible"}, 0.7)}, "uncertain",
     "model:low_confidence"),
    ("optional not visible is fine", {"verdict": v({**ALL_PASS, "c_opt": "not_visible"})}, "pass", "model:pass"),
    ("error id but no failing check → inconsistent", {"verdict": v(ALL_PASS, 0.95, ["E_X"])}, "uncertain",
     "model:inconsistent E_X"),
    ("unknown error id ignored", {"verdict": v(ALL_PASS, 0.95, ["E_OTHER_STEP"])}, "pass", "model:pass"),
    ("checks from another step ignored", {"verdict": v({**ALL_PASS, "c_zzz": "fail"})}, "pass", "model:pass"),
    ("duplicate check id: first wins", {"verdict": PerceptionVerdict(step_id="s3", checks=[
        CheckResult(id="c_a", result="pass", observation="o"), CheckResult(id="c_a", result="fail", observation="o"),
        CheckResult(id="c_b", result="pass", observation="o"), CheckResult(id="c_fine", result="pass", observation="o")],
        confidence=0.9, spoken_feedback="s")}, "pass", "model:pass"),
    ("no verdict", {"verdict": None}, "uncertain", "model:no_verdict"),
    ("quality gate fails first", {"verdict": v(ALL_PASS), "quality": QualityReport(ok=False, failing=["glare"])},
     "uncertain", "quality:glare"),
    ("quality ok passes through", {"verdict": v(ALL_PASS), "quality": QualityReport(ok=True)}, "pass", "model:pass"),
]

LED_CASES: list[tuple[str, dict[str, Any], str, str]] = [
    ("strong not lit beats model pass", {"verdict": v({"c_led_lit": "pass"}, 0.99, step_id="s6"),
                                         "led": LedResult(lit=False, signal_strength=0.95)}, "fix", "led:not_lit"),
    ("strong lit beats model fail", {"verdict": v({"c_led_lit": "fail"}, 0.9, step_id="s6"),
                                     "led": LedResult(lit=True, signal_strength=0.8)}, "pass", "led:lit"),
    ("weak LED evidence falls through", {"verdict": v({"c_led_lit": "fail"}, 0.9, step_id="s6"),
                                         "led": LedResult(lit=False, signal_strength=0.3)}, "fix", "model:fail c_led_lit"),
    ("LED step quality fail", {"verdict": None, "led": LedResult(lit=True, signal_strength=0.9),
                               "quality": QualityReport(ok=False, failing=["dark"])}, "uncertain", "quality:dark"),
]


@pytest.mark.parametrize(("name", "kw", "status", "reason"), CASES, ids=[c[0] for c in CASES])
def test_decision_table(name: str, kw: dict[str, Any], status: str, reason: str) -> None:
    d = decide(kw.get("verdict"), STEP, quality=kw.get("quality"), led=kw.get("led"))
    assert (d.status, d.reason) == (status, reason)


@pytest.mark.parametrize(("name", "kw", "status", "reason"), LED_CASES, ids=[c[0] for c in LED_CASES])
def test_led_cross_check(name: str, kw: dict[str, Any], status: str, reason: str) -> None:
    d = decide(kw.get("verdict"), LED_STEP, quality=kw.get("quality"), led=kw.get("led"))
    assert (d.status, d.reason) == (status, reason)


def test_uncertain_always_has_a_specific_retake() -> None:
    d = decide(None, STEP, quality=QualityReport(ok=False, failing=["dark"]))
    assert "too dark" in (d.retake_instruction or "")
    d2 = decide(v({**ALL_PASS, "c_b": "not_visible"}, retake="Move your hand."), STEP)
    assert d2.retake_instruction == "Move your hand."
    d3 = decide(v({**ALL_PASS, "c_b": "not_visible"}), STEP)
    assert d3.retake_instruction  # generic fallback


def test_pass_partial_lists_double_check() -> None:
    d = decide(v({**ALL_PASS, "c_fine": "not_visible"}), STEP)
    assert d.double_check == ["c_fine"]


@pytest.mark.parametrize(("status", "conf", "expected"), [
    ("pass", 0.79, True), ("pass", 0.81, False), ("fix", 0.65, True), ("pass_partial", 0.78, True),
    ("uncertain", 0.6, False)])
def test_needs_second_look(status: str, conf: float, expected: bool) -> None:
    d = Decision(status, "model:x")  # type: ignore[arg-type]
    assert needs_second_look(d, v(ALL_PASS, conf), (0.5, 0.8)) is expected


def test_second_look_never_for_led_decisions() -> None:
    assert not needs_second_look(Decision("pass", "led:lit"), v({"c_led_lit": "pass"}, 0.7), (0.5, 0.8))


def test_combine_second_look() -> None:
    assert combine_second_look(Decision("pass", "model:pass"), Decision("pass", "model:pass")).status == "pass"
    merged = combine_second_look(Decision("pass", "model:pass"), Decision("pass_partial", "model:pass_partial", ["c"]))
    assert (merged.status, merged.double_check) == ("pass_partial", ["c"])
    dis = combine_second_look(Decision("pass", "model:pass"), Decision("fix", "model:fail c_a"))
    assert (dis.status, dis.reason) == ("uncertain", "second_look_disagreement")
    assert combine_second_look(Decision("fix", "model:fail c_a"), Decision("uncertain", "x")).status == "uncertain"
