"""Help-request triage with Nemotron Super (BUILD_PROMPT.md 9.5.3, 12.1).

When a help request is created, the student's attempt history for that step is summarised for the TA in the
background, so the bench UI immediately shows "Your TA has been notified" and never waits on this call.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from collections import Counter
from typing import Any

from polarity.llm.prompts import DIAGNOSIS_SYSTEM
from polarity.llm.router import RouterError
from polarity.models.session import HelpRequest
from polarity.models.verdict import Diagnosis

log = logging.getLogger(__name__)


def attempt_history(rt: Any, help_req: HelpRequest) -> dict[str, Any]:
    """Factual input for the diagnosis: verdicts, failed checks, error ids, hint levels, timestamps."""
    session = rt.db.get_session(help_req.session_id)
    lab = rt.labs.get(session.lab_id) if session else None
    step = lab.step(help_req.step_id) if lab else None
    attempts = []
    errors: Counter[str] = Counter()
    fixes = uncertain = 0
    for a in rt.db.list_attempts(help_req.session_id, help_req.step_id):
        entry: dict[str, Any] = {"at": a.created_at, "kind": a.kind, "status": a.status, "reason": a.reason,
                                 "hint_level": a.hint_level, "confidence": a.confidence}
        if a.verdict_json:
            try:
                data = json.loads(a.verdict_json)
            except json.JSONDecodeError:
                data = {}
            p = data.get("perception") or {}
            entry["failed_checks"] = [c.get("id") for c in p.get("checks") or [] if c.get("result") == "fail"]
            entry["not_visible_checks"] = [c.get("id") for c in p.get("checks") or [] if c.get("result") == "not_visible"]
            entry["error_ids"] = p.get("detected_error_ids") or []
            errors.update(entry["error_ids"])
            if a.kind == "ask":
                entry["question"] = data.get("question")
                entry["answer"] = data.get("answer")
            elif p.get("student_answer"):
                entry["answer_to_student"] = p.get("student_answer")
        fixes += a.status == "fix"
        uncertain += a.status == "uncertain"
        attempts.append(entry)
    top = errors.most_common(1)
    return {
        "alias": session.student_alias if session else None, "bench_id": session.bench_id if session else None,
        "lab": lab.title if lab else None, "step_id": help_req.step_id, "step_title": step.title if step else None,
        "trigger": help_req.trigger, "fix_count": fixes, "uncertain_count": uncertain,
        "top_error": top[0][0] if top else None,
        "top_error_meaning": (step.error(top[0][0]).description if step and top and step.error(top[0][0]) else None),
        "attempts": attempts,
    }


def diagnose(rt: Any, help_req: HelpRequest) -> dict[str, Any]:
    """Ask the reasoning model for a TA summary; returns the stored summary dict (never raises)."""
    history = attempt_history(rt, help_req)
    try:
        res = rt.router.call("reasoning", [{"role": "system", "content": DIAGNOSIS_SYSTEM},
                                           {"role": "user", "content": json.dumps(history, ensure_ascii=False)}],
                             schema=Diagnosis, max_tokens=500, interactive=False)
        summary = res.parsed.model_dump() if res.parsed else {}  # type: ignore[union-attr]
        if help_req.trigger == "safety":
            summary["urgency"] = "high"  # deterministic: safety is always urgent
        summary.update({"model_id": res.model_id, "latency_ms": res.latency_ms})
    except RouterError as exc:
        log.warning("diagnosis failed: %s", exc)
        summary = {"unavailable": True, "reason": str(exc)}
    try:
        rt.db.update_help_summary(help_req.id, summary)
        updated = rt.db.get_help(help_req.id)
        if updated is not None:
            rt.hub_send("help", updated.model_dump())  # the hub's TA card gets the summary too
        payload = rt.help_payload(updated)
        rt.bus.publish("help_updated", payload)
    except sqlite3.ProgrammingError:  # the server shut down (database closed) while the model was answering
        log.info("diagnosis for %s dropped: database closed", help_req.id)
    return summary


def diagnose_async(rt: Any, help_req: HelpRequest) -> threading.Thread:
    thread = threading.Thread(target=diagnose, args=(rt, help_req), name=f"diagnose-{help_req.id[:6]}", daemon=True)
    thread.start()
    return thread
