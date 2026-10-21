"""Deterministic decision policy (BUILD_PROMPT.md 9.4). Code, not the model, decides pass/fix/uncertain.

Pure functions only, fully unit-tested. On top of the spec's rules, one conservative rule is added (logged in
docs/DECISIONS.md): if the model lists a known error id for this step but marks no check as failed, its output
is inconsistent and the result is CAN'T TELL, never a pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from polarity.edge.quality import RETAKE_INSTRUCTIONS
from polarity.models.lab import Step
from polarity.models.verdict import LedResult, PerceptionVerdict, QualityReport, Status

GENERIC_RETAKE = "Hold the board still with your hands out of the frame and good light on it, then press Check again."

_OUTCOME_CLASS = {"pass": "passing", "pass_partial": "passing", "fix": "fix", "uncertain": "uncertain"}


@dataclass
class Decision:
    status: Status
    reason: str
    double_check: list[str] = field(default_factory=list)   # allow_uncertain check ids that were not visible
    retake_instruction: str | None = None


def _uncertain(reason: str, v: PerceptionVerdict | None = None, retake: str | None = None) -> Decision:
    return Decision("uncertain", reason, [], retake or (v.retake_instruction if v and v.retake_instruction else None)
                    or GENERIC_RETAKE)


def decide(v: PerceptionVerdict | None, step: Step, *, pass_min_conf: float = 0.75, fix_min_conf: float = 0.60,
           led: LedResult | None = None, quality: QualityReport | None = None,
           led_strong_min: float = 0.60) -> Decision:
    """Turn a validated perception verdict (plus edge evidence) into a final status."""
    if quality is not None and not quality.ok:
        metric = quality.failing[0]
        return Decision("uncertain", f"quality:{metric}", [], RETAKE_INSTRUCTIONS.get(metric, GENERIC_RETAKE))

    if step.led_check is not None and led is not None:
        expect = step.led_check.expect_lit
        strong = led.signal_strength >= led_strong_min
        if strong and led.lit != expect:  # physical evidence wins: a fail cannot be talked into a pass
            return Decision("fix", "led:not_lit" if expect else "led:lit_unexpectedly")
        if strong and led.lit == expect:
            return Decision("pass", "led:lit" if expect else "led:off")

    if v is None:
        return _uncertain("model:no_verdict")

    step_ids = {c.id for c in step.checks}
    results = {}
    for c in v.checks:
        if c.id in step_ids and c.id not in results:
            results[c.id] = c
    fails = [cid for cid, c in results.items() if c.result == "fail"]
    missing = [c.id for c in step.checks if c.required and (c.id not in results or results[c.id].result == "not_visible")]
    hard_missing = [cid for cid in missing if not step.check(cid).allow_uncertain]  # type: ignore[union-attr]
    known_errors = [e for e in v.detected_error_ids if step.error(e) is not None]

    if fails and v.confidence >= fix_min_conf:
        return Decision("fix", "model:fail " + ",".join(fails))
    if fails:
        return _uncertain("model:low_confidence_fail", v)
    if known_errors:
        return _uncertain("model:inconsistent " + ",".join(known_errors), v)
    if not missing and v.confidence >= pass_min_conf:
        return Decision("pass", "model:pass")
    if missing and not hard_missing and v.confidence >= pass_min_conf:
        return Decision("pass_partial", "model:pass_partial", list(missing))
    if hard_missing:
        return _uncertain("model:not_visible " + ",".join(hard_missing), v)
    return _uncertain("model:low_confidence", v)


def needs_second_look(d: Decision, v: PerceptionVerdict | None, grey_zone: tuple[float, float]) -> bool:
    """Grey-zone confidence on a model-based pass/fix/pass_partial triggers one closer look."""
    if v is None or d.status == "uncertain" or not d.reason.startswith("model:"):
        return False
    lo, hi = grey_zone
    return lo <= v.confidence <= hi


def combine_second_look(first: Decision, second: Decision) -> Decision:
    """Keep the result only if both looks agree on the outcome class; the more cautious status wins."""
    if _OUTCOME_CLASS[first.status] != _OUTCOME_CLASS[second.status]:
        return Decision("uncertain", "second_look_disagreement", [],
                        second.retake_instruction or first.retake_instruction or GENERIC_RETAKE)
    if "pass_partial" in (first.status, second.status):
        merged = list(dict.fromkeys(first.double_check + second.double_check))
        return Decision("pass_partial", first.reason + "+second_look", merged)
    return Decision(first.status, first.reason + "+second_look", first.double_check)
