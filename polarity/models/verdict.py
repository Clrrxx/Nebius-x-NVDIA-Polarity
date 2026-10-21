"""Verdict schemas (BUILD_PROMPT.md 9.3).

``PerceptionVerdict`` is what the model returns (validated, JSON-schema enforced where supported);
``FinalVerdict`` is what deterministic code decides. ``evidence_region`` is typed as a small model with
x/y/w/h fractions (the spec's ``{"x","y","w","h"}`` dict) so ``additionalProperties: false`` holds everywhere.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Status = Literal["pass", "pass_partial", "fix", "uncertain"]


class EvidenceRegion(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(ge=0, le=1)
    h: float = Field(ge=0, le=1)


class CheckResult(BaseModel):
    id: str
    result: Literal["pass", "fail", "not_visible"]
    observation: str                       # ≤ 25 words, cites visual evidence


class PerceptionVerdict(BaseModel):        # what the model returns
    step_id: str
    checks: list[CheckResult]
    detected_error_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)  # honest probability the overall judgement is right
    evidence_region: EvidenceRegion | None = None   # approximate; optional
    retake_instruction: str | None = None  # when anything is not_visible
    spoken_feedback: str                   # ≤ 25 words
    student_answer: str | None = None      # if student audio/question was attached (≤ 40 words)
    parts_seen: list[str] = Field(default_factory=list)  # printed part markings read (e.g. "NE555")


class QualityReport(BaseModel):
    ok: bool
    metrics: dict[str, float | int | None] = Field(default_factory=dict)
    failing: list[str] = Field(default_factory=list)


class LedResult(BaseModel):
    lit: bool
    signal_strength: float = Field(ge=0, le=1)
    blobs: list[dict[str, Any]] = Field(default_factory=list)
    baseline_used: bool = False
    note: str | None = None


class FinalVerdict(BaseModel):             # what code decides
    status: Status
    reason: str                            # e.g. "quality:glare", "model:fail c_orientation", "led:not_lit"
    perception: PerceptionVerdict | None = None
    led: dict[str, Any] | None = None
    second_look_used: bool = False
    model_id: str | None = None
    latency_ms: int | None = None
    cost_usd: float | None = None
    # UI/context extras (not decided by the model)
    step_id: str | None = None
    retake_instruction: str | None = None
    quality: QualityReport | None = None
    hint_level: int | None = None
    hint_text: str | None = None
    double_check: list[str] = Field(default_factory=list)   # allow_uncertain checks that were not visible
    attempt_id: str | None = None
    warped_url: str | None = None
    error: str | None = None


class VoiceAnswer(BaseModel):
    answer: str
    intent: Literal["how_to", "why", "part_info", "help", "other"] = "other"
    parts_mentioned: list[str] = Field(default_factory=list)


class AudioTranscript(BaseModel):          # omni_separate: audio-only call returns transcript + intent
    transcript: str
    intent: Literal["how_to", "why", "part_info", "help", "other"] = "other"


class IntentLabel(BaseModel):
    intent: Literal["how_to", "why", "part_info", "help", "other"]
    part_number: str | None = None


class ShortText(BaseModel):
    text: str


class Diagnosis(BaseModel):
    summary_for_ta: str
    likely_root_cause: str
    suggested_ta_action: str
    urgency: Literal["low", "medium", "high"]


class AuditSuspect(BaseModel):
    step_id: str
    check_id: str
    why: str
    confidence: float = Field(ge=0, le=1)


class BoardAudit(BaseModel):
    suspects: list[AuditSuspect]
    spoken_feedback: str


class PinInfo(BaseModel):
    pin: str
    name: str


class PartSummary(BaseModel):
    summary: str
    pinout: list[PinInfo] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)


class PageStep(BaseModel):
    title: str
    instruction: str
    figure_description: str | None = None


class PageExtract(BaseModel):
    page_summary: str
    components: list[str] = Field(default_factory=list)
    steps_found: list[PageStep] = Field(default_factory=list)
