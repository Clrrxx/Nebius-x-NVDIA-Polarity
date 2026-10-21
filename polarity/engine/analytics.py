"""Class analytics for the TA dashboard and the end-of-class report (all numbers come from the database).

Heatmap cell states (BUILD_PROMPT.md 11.4): not started · in progress · passed first try · passed after fixes
(with attempt count) · struggling (≥2 fixes) · stuck (≥3 fixes or an open help request); plus a "many can't-tell"
flag (≥2 CAN'T TELL results on that step).
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from polarity.models.lab import LabDefinition
from polarity.models.session import Attempt, HelpRequest, Session

PASSING = ("pass", "pass_partial")
DECISIVE = ("pass", "pass_partial", "fix")
ACTIVE_WINDOW = timedelta(minutes=30)


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _detected(a: Attempt) -> list[str]:
    if not a.verdict_json:
        return []
    try:
        data = json.loads(a.verdict_json)
    except json.JSONDecodeError:
        return []
    perception = data.get("perception") or {}
    return list(perception.get("detected_error_ids") or [])


def _observations(a: Attempt) -> list[dict[str, Any]]:
    if not a.verdict_json:
        return []
    try:
        data = json.loads(a.verdict_json)
    except json.JSONDecodeError:
        return []
    perception = data.get("perception") or {}
    return [{"id": c.get("id"), "result": c.get("result"), "observation": c.get("observation")}
            for c in perception.get("checks") or []]


class ClassData:
    """Sessions, attempts and help requests for one lab, loaded once and reused by every metric."""

    def __init__(self, db: Any, lab: LabDefinition) -> None:
        self.lab = lab
        self.sessions: list[Session] = db.list_sessions(lab.id)
        ids = {s.id for s in self.sessions}
        self.attempts: dict[str, list[Attempt]] = {s.id: db.list_attempts(s.id) for s in self.sessions}
        self.help: list[HelpRequest] = [h for h in db.list_help(None) if h.session_id in ids]

    def checks(self, session_id: str, step_id: str) -> list[Attempt]:
        return [a for a in self.attempts[session_id] if a.step_id == step_id and a.kind == "check"]

    def passed_at(self, session_id: str, step_id: str) -> datetime | None:
        for a in self.attempts[session_id]:
            if a.step_id == step_id and (a.kind == "ta_skip" or (a.kind == "check" and a.status in PASSING)):
                return _dt(a.created_at)
        return None


def cell_state(checks: list[Attempt], passed: bool, open_help: bool, is_current: bool) -> dict[str, Any]:
    fixes = sum(a.status == "fix" for a in checks)
    uncertain = sum(a.status == "uncertain" for a in checks)
    if passed:
        state = "passed_first" if fixes == 0 else "passed_after"
    elif fixes >= 3 or open_help:
        state = "stuck"
    elif fixes >= 2:
        state = "struggling"
    elif is_current:
        state = "in_progress"
    else:
        state = "not_started"
    return {"state": state, "attempts": len(checks), "fixes": fixes, "uncertain": uncertain,
            "cant_tell": uncertain >= 2, "help": open_help}


def heatmap(data: ClassData) -> dict[str, Any]:
    lab = data.lab
    rows = []
    for s in data.sessions:
        open_steps = {h.step_id for h in data.help if h.session_id == s.id and h.status == "open"}
        current_found = False
        cells = []
        for step in lab.steps:
            passed = data.passed_at(s.id, step.id) is not None
            is_current = not passed and not current_found and s.completed_at is None
            if is_current:
                current_found = True
            cell = cell_state(data.checks(s.id, step.id), passed, step.id in open_steps, is_current)
            cell["step_id"] = step.id
            cells.append(cell)
        rows.append({"session_id": s.id, "alias": s.student_alias, "bench_id": s.bench_id,
                     "completed": s.completed_at is not None, "is_simulated": s.is_simulated, "cells": cells})
    rows.sort(key=lambda r: (r["bench_id"] or "~", r["alias"].lower()))
    return {"steps": [{"id": st.id, "title": st.title} for st in lab.steps], "rows": rows}


def step_insights(data: ClassData) -> list[dict[str, Any]]:
    out = []
    for step in data.lab.steps:
        attempted = first_pass = 0
        attempts_to_pass: list[int] = []
        errors: Counter[str] = Counter()
        total_checks = uncertain = 0
        for s in data.sessions:
            checks = data.checks(s.id, step.id)
            total_checks += len(checks)
            uncertain += sum(a.status == "uncertain" for a in checks)
            decisive = [a for a in checks if a.status in DECISIVE]
            if decisive:
                attempted += 1
                if decisive[0].status in PASSING:
                    first_pass += 1
            for i, a in enumerate(checks):
                if a.status in PASSING:
                    attempts_to_pass.append(i + 1)
                    break
            for a in checks:
                if a.status == "fix":
                    errors.update(e for e in _detected(a) if step.error(e))
        out.append({
            "step_id": step.id, "title": step.title, "students_attempted": attempted,
            "first_try_pass_pct": round(100.0 * first_pass / attempted) if attempted else None,
            "median_attempts": round(statistics.median(attempts_to_pass), 1) if attempts_to_pass else None,
            "uncertain_rate_pct": round(100.0 * uncertain / total_checks) if total_checks else None,
            "checks": total_checks,
            "top_errors": [{"error_id": e, "label": step.error(e).description if step.error(e) else e, "count": n}  # type: ignore[union-attr]
                           for e, n in errors.most_common(3)],
        })
    return out


def step_durations(data: ClassData) -> list[float]:
    """Seconds from the previous pass (or session start) to each step's pass."""
    out = []
    for s in data.sessions:
        prev = _dt(s.started_at)
        for step in data.lab.steps:
            at = data.passed_at(s.id, step.id)
            if at is None:
                break
            out.append(max(0.0, (at - prev).total_seconds()))
            prev = at
    return out


def overview(data: ClassData, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now().astimezone()
    active = 0
    for s in data.sessions:
        if s.completed_at is not None:
            continue
        times = [_dt(s.started_at)] + [_dt(a.created_at) for a in data.attempts[s.id]]
        if now - max(times) <= ACTIVE_WINDOW:
            active += 1
    durations = step_durations(data)
    return {
        "lab": {"id": data.lab.id, "title": data.lab.title, "steps": [{"id": st.id, "title": st.title}
                                                                       for st in data.lab.steps]},
        "sessions": len(data.sessions),
        "active_benches": active,
        "completed": sum(s.completed_at is not None for s in data.sessions),
        "waiting_for_help": sum(h.status == "open" for h in data.help),
        "median_step_seconds": round(statistics.median(durations)) if durations else None,
        "simulated": any(s.is_simulated for s in data.sessions),
        "insights": step_insights(data),
    }


def timeline(db: Any, lab: LabDefinition | None, session_id: str, step_id: str | None = None) -> list[dict[str, Any]]:
    """Attempt history for the TA drawer (thumbnails, statuses, observations, model, latency)."""
    items = []
    for a in db.list_attempts(session_id, step_id):
        step = lab.step(a.step_id) if lab else None
        entry: dict[str, Any] = {
            "id": a.id, "created_at": a.created_at, "step_id": a.step_id, "step_title": step.title if step else a.step_id,
            "kind": a.kind, "status": a.status, "reason": a.reason, "hint_level": a.hint_level,
            "confidence": a.confidence, "model_id": a.model_id, "latency_ms": a.latency_ms, "cost_usd": a.cost_usd,
            "thumb": f"/media/{a.warped_image_path}" if a.warped_image_path else None,
            "observations": _observations(a), "detected_error_ids": _detected(a), "is_simulated": a.is_simulated,
        }
        if a.kind == "ask" and a.verdict_json:
            try:
                qa = json.loads(a.verdict_json)
                entry.update({"question": qa.get("question"), "answer": qa.get("answer")})
            except json.JSONDecodeError:
                pass
        items.append(entry)
    return items


def labs_with_sessions(db: Any) -> list[str]:
    seen: dict[str, None] = {}
    for s in db.list_sessions():
        seen.setdefault(s.lab_id, None)
    return list(seen)
