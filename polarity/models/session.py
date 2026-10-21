"""Session, attempt, help-request and report records (mirrors the SQLite tables in storage/db.py)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Session(BaseModel):
    id: str
    student_alias: str
    bench_id: str | None = None
    lab_id: str
    started_at: str
    completed_at: str | None = None
    is_simulated: bool = False


class Attempt(BaseModel):
    id: str
    session_id: str
    step_id: str
    kind: Literal["check", "ask", "audit", "ta_skip"] = "check"
    status: str | None = None              # pass | pass_partial | fix | uncertain | answered | error | skipped
    reason: str | None = None
    confidence: float | None = None
    hint_level: int | None = None
    verdict_json: str | None = None
    led_json: str | None = None
    raw_image_path: str | None = None
    warped_image_path: str | None = None
    audio_path: str | None = None
    model_id: str | None = None
    latency_ms: int | None = None
    cost_usd: float | None = None
    created_at: str
    is_simulated: bool = False


class HelpRequest(BaseModel):
    id: str
    session_id: str
    step_id: str
    trigger: str                           # fix_count | uncertain_streak | call_ta | power_test | safety
    summary_json: str | None = None
    status: Literal["open", "resolved"] = "open"
    created_at: str
    resolved_at: str | None = None
    is_simulated: bool = False


class Report(BaseModel):
    id: str
    lab_id: str
    created_at: str
    model_id: str | None = None
    markdown: str
    input_stats_json: str
    cost_usd: float | None = None


class StepProgress(BaseModel):
    step_id: str
    fix_count: int = 0
    uncertain_streak: int = 0
    hint_level: int = 1
    checks: int = 0
    power_test_fails: int = 0
    passed: bool = False


class SessionState(BaseModel):
    """What the bench UI needs to render the current session."""

    session: Session
    lab_id: str
    lab_title: str
    current_index: int
    current_step_id: str | None
    completed: bool
    progress: list[StepProgress]
    total_checks: int = 0
    elapsed_s: int = 0
    open_help: list[dict[str, Any]] = Field(default_factory=list)
