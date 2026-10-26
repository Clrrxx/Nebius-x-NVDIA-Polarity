"""The "Check my step" pipeline (BUILD_PROMPT.md 4.3).

frame → BoardLocator warp → QualityGate (fail → local CAN'T TELL, no cloud call) → LedDetector (power test)
→ perception call on Nemotron Nano Omni (image ± student audio, schema-validated) → deterministic decision
→ second look on a zoomed re-warp when confidence is in the grey zone → FinalVerdict.

Persistence and state changes live in the session engine; this module is also used by the eval harness.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from polarity.edge.board import BoardLocator
from polarity.edge.led import LedDetector
from polarity.edge.quality import QualityGate
from polarity.engine.decision import Decision, combine_second_look, decide, needs_second_look
from polarity.llm import prompts
from polarity.llm.router import InvalidModelOutput, ModelRouter, RouterError, RouterResult
from polarity.models.lab import LabDefinition, Step
from polarity.models.verdict import (
    AudioTranscript,
    FinalVerdict,
    LedResult,
    PerceptionVerdict,
    QualityReport,
    ShortText,
)

log = logging.getLogger(__name__)


def encode_jpeg(img: np.ndarray, max_long_side: int = 1280, quality: int = 85) -> bytes:
    """JPEG bytes, downscaled so the long side is at most ``max_long_side``."""
    h, w = img.shape[:2]
    if max(h, w) > max_long_side:
        scale = max_long_side / float(max(h, w))
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
    if not ok:
        raise ValueError("JPEG encoding failed")
    return buf.tobytes()


@dataclass
class CheckRequest:
    lab: LabDefinition
    step: Step
    frame: np.ndarray
    hint_level: int = 1
    typed_question: str | None = None
    audio_wav: bytes | None = None
    motion: float | None = None
    led_baseline: np.ndarray | None = None
    session_id: str | None = None
    mock_hint: str | None = None


@dataclass
class CheckOutcome:
    final: FinalVerdict
    raw: np.ndarray
    warped: np.ndarray | None
    quality: QualityReport
    led: LedResult | None = None
    calls: list[RouterResult] = field(default_factory=list)
    transcript: str | None = None
    second_look_image: np.ndarray | None = None


def next_step_title(lab: LabDefinition, step: Step) -> str | None:
    idx = lab.step_index(step.id)
    return lab.steps[idx + 1].title if idx + 1 < len(lab.steps) else None


class Verifier:
    def __init__(self, config: Any, router: ModelRouter, locator: BoardLocator | None = None,
                 gate: QualityGate | None = None, led: LedDetector | None = None) -> None:
        self.config = config
        self.router = router
        self.locator = locator or BoardLocator.from_config(config)
        self.gate = gate or QualityGate(config.settings.quality, config.env.markers_enabled)
        self.led = led or LedDetector(config.settings.led)

    # ── edge helpers ─────────────────────────────────────────────────────────────────────────

    def analyse(self, frame: np.ndarray, motion: float | None = None) -> tuple[Any, np.ndarray | None, QualityReport]:
        """Locate + warp + quality for one frame (used by the check and the live quality chips)."""
        det = self.locator.detect(frame)
        warped = self.locator.warp(frame, det)
        markers = det.markers_found if self.config.env.markers_enabled else None
        quality = self.gate.evaluate(warped if warped is not None else frame, markers, motion,
                                     board_found=det.found if self.config.env.markers_enabled else None,
                                     focus_image=self.locator.region(frame, det))
        return det, warped, quality

    def _encode(self, img: np.ndarray) -> bytes:
        s = self.config.settings.images
        return encode_jpeg(img, s.max_long_side, s.jpeg_quality)

    # ── pipeline ─────────────────────────────────────────────────────────────────────────────

    def check(self, req: CheckRequest) -> CheckOutcome:
        """Run one check. Raises RouterError subclasses (budget, unavailable, call failed) for the UI to show."""
        det, warped, quality = self.analyse(req.frame, req.motion)
        settings = self.config.settings
        if not quality.ok or warped is None:
            d = decide(None, req.step, quality=quality)
            return CheckOutcome(final=self._final(d, req, None, quality=quality), raw=req.frame, warped=warped,
                                quality=quality)

        led: LedResult | None = None
        if req.step.led_check is not None:
            led = self.led.detect(warped, req.led_baseline, req.step.led_check.colour)

        calls: list[RouterResult] = []
        typed = req.typed_question
        transcript = None
        audio_for_call: bytes | None = None
        mode = self.config.audio_mode()
        variant = self.config.capabilities.audio_input.variant or "input_audio"
        if req.audio_wav:
            if mode == "omni_combined" or self.config.mock:
                audio_for_call = req.audio_wav
            elif mode == "omni_separate":
                res = self.router.call("perception", prompts.transcribe_messages(req.audio_wav, variant),
                                       schema=AudioTranscript, max_tokens=200, session_id=req.session_id,
                                       mock_hint=req.mock_hint)
                calls.append(res)
                transcript = res.parsed.transcript if res.parsed else None  # type: ignore[union-attr]
                typed = " ".join(t for t in (typed, transcript) if t) or None

        image = self._encode(warped)
        try:
            first = self._perceive(req, image, typed, audio_for_call, variant, second_look=False)
        except InvalidModelOutput:
            d = Decision("uncertain", "model:invalid_output", [], "Please press Check again.")
            return CheckOutcome(final=self._final(d, req, None, quality=quality, calls=calls, led=led), raw=req.frame,
                                warped=warped, quality=quality, led=led, calls=calls, transcript=transcript)
        calls.append(first)
        v1: PerceptionVerdict = first.parsed  # type: ignore[assignment]
        dec = self._decide(v1, req.step, led, quality)
        second_used = False
        zoom_img = None
        if needs_second_look(dec, v1, tuple(settings.decision.grey_zone)):
            region = v1.evidence_region
            centre = (region.x + region.w / 2, region.y + region.h / 2) if region else (0.5, 0.5)
            zoom_img = self.locator.zoom_crop(req.frame, det, centre, settings.decision.second_look_zoom)
            second_used = True
            try:
                second = self._perceive(req, self._encode(zoom_img if zoom_img is not None else warped), typed, None,
                                        variant, second_look=True)
                calls.append(second)
                dec = combine_second_look(dec, self._decide(second.parsed, req.step, led, quality))  # type: ignore[arg-type]
            except (InvalidModelOutput, RouterError) as exc:
                log.warning("second look failed: %s", exc)
                dec = Decision("uncertain", "second_look_failed", [], "Please press Check again.")
        self._shorten(v1, req, calls)
        final = self._final(dec, req, v1, quality=quality, calls=calls, led=led, second_look=second_used)
        return CheckOutcome(final=final, raw=req.frame, warped=warped, quality=quality, led=led, calls=calls,
                            transcript=transcript, second_look_image=zoom_img)

    def _perceive(self, req: CheckRequest, image: bytes, typed: str | None, audio: bytes | None, variant: str,
                  second_look: bool) -> RouterResult:
        settings = self.config.settings.decision
        messages = prompts.verifier_messages(req.lab, req.step, image, req.hint_level, typed, audio,
                                             variant if audio else None, next_step_title(req.lab, req.step),
                                             second_look=second_look)
        return self.router.call("perception", messages, schema=PerceptionVerdict,
                                temperature=settings.second_look_temperature if second_look else 0.0,
                                max_tokens=900, session_id=req.session_id, mock_hint=req.mock_hint)

    def _decide(self, v: PerceptionVerdict, step: Step, led: LedResult | None, quality: QualityReport) -> Decision:
        s = self.config.settings
        return decide(v, step, pass_min_conf=s.decision.pass_min_conf, fix_min_conf=s.decision.fix_min_conf,
                      led=led, quality=quality, led_strong_min=s.led.strong_min)

    def _shorten(self, v: PerceptionVerdict, req: CheckRequest, calls: list[RouterResult]) -> None:
        """Keep spoken text within its word limits; uses the cheap fast_text model only when needed."""
        for attr, limit in (("spoken_feedback", 25), ("student_answer", 40)):
            text = getattr(v, attr)
            if not text or len(text.split()) <= limit:
                continue
            try:
                res = self.router.call("fast_text", [
                    {"role": "system", "content": prompts.shorten_system(limit)},
                    {"role": "user", "content": f'{{"max_words": {limit}, "text": {text!r}}}'}],
                    schema=ShortText, max_tokens=200, session_id=req.session_id)
                calls.append(res)
                setattr(v, attr, res.parsed.text if res.parsed else " ".join(text.split()[:limit]))  # type: ignore[union-attr]
            except RouterError:
                setattr(v, attr, " ".join(text.split()[:limit]))

    def _final(self, d: Decision, req: CheckRequest, v: PerceptionVerdict | None, *, quality: QualityReport,
               calls: list[RouterResult] | None = None, led: LedResult | None = None,
               second_look: bool = False) -> FinalVerdict:
        calls = calls or []
        perception_calls = [c for c in calls if c.role == "perception"]
        model_id = perception_calls[0].model_id if perception_calls else None
        latency = sum(c.latency_ms for c in calls) if calls else None
        costs = [c.cost_usd for c in calls]
        cost = None if not calls or any(c is None for c in costs) else round(sum(costs), 6)  # type: ignore[arg-type]
        hint = None
        if d.status == "fix":
            for err_id in (v.detected_error_ids if v else []):
                err = req.step.error(err_id)
                if err:
                    hint = err.hint(req.hint_level)
                    break
            if hint is None and d.reason == "led:not_lit" and req.step.common_errors:
                hint = req.step.common_errors[0].hint(req.hint_level)
        double = [req.step.check(c).statement for c in d.double_check if req.step.check(c)]  # type: ignore[union-attr]
        return FinalVerdict(status=d.status, reason=d.reason, perception=v,
                            led=led.model_dump() if led else None, second_look_used=second_look, model_id=model_id,
                            latency_ms=latency, cost_usd=cost, step_id=req.step.id,
                            retake_instruction=d.retake_instruction if d.status == "uncertain" else None,
                            quality=quality, hint_level=req.hint_level, hint_text=hint, double_check=double)
