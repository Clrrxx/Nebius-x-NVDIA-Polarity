"""End-of-class TA report (BUILD_PROMPT.md 12.2) written by Nemotron Ultra (falls back to Super).

Statistics are aggregated in code from the database and passed as JSON; the prompt forbids the model from
inventing numbers. If the data includes simulated records the first line must say so: this is enforced in code
too, not left to the model. Markdown is rendered with raw HTML disabled before it reaches the browser.
"""

from __future__ import annotations

import html
import json
import statistics
import time
from collections import Counter
from datetime import datetime
from typing import Any

import markdown

from polarity.engine.analytics import ClassData, overview
from polarity.llm.prompts import CLASS_REPORT_SYSTEM
from polarity.models.session import Report
from polarity.storage.db import new_id, now_iso

SIMULATED_NOTE = "**Note: this report includes simulated class data for demonstration — these are not real results.**"


def class_stats(data: ClassData) -> dict[str, Any]:
    """Aggregate everything the report may cite. Every number in the report must come from here."""
    ov = overview(data)
    lab = data.lab
    quality: Counter[str] = Counter()
    errors: Counter[str] = Counter()
    checks = uncertain = 0
    for atts in data.attempts.values():
        for a in atts:
            if a.kind != "check":
                continue
            checks += 1
            uncertain += a.status == "uncertain"
            if a.reason and a.reason.startswith("quality:"):
                quality[a.reason.split(":", 1)[1]] += 1
            if a.status == "fix" and a.verdict_json:
                try:
                    perception = json.loads(a.verdict_json).get("perception") or {}
                except json.JSONDecodeError:
                    perception = {}
                errors.update(perception.get("detected_error_ids") or [])
    completion_minutes = [round((datetime.fromisoformat(s.completed_at) - datetime.fromisoformat(s.started_at)).total_seconds() / 60, 1)
                          for s in data.sessions if s.completed_at]
    follow_up = []
    stuck_help = {(h.session_id, h.step_id) for h in data.help}
    for s in data.sessions:
        reasons = []
        for step in lab.steps:
            fixes = sum(a.status == "fix" for a in data.checks(s.id, step.id))
            if fixes >= 3:
                reasons.append(f"{fixes} FIX verdicts on {step.title}")
            elif (s.id, step.id) in stuck_help:
                reasons.append(f"asked for help on {step.title}")
        if not s.completed_at and not reasons:
            done = sum(1 for step in lab.steps if data.passed_at(s.id, step.id))
            if done < len(lab.steps) // 2:
                reasons.append(f"completed {done} of {len(lab.steps)} steps so far")
        if reasons:
            follow_up.append({"alias": s.student_alias, "reason": "; ".join(reasons[:2])})
    simulated = sum(s.is_simulated for s in data.sessions)
    return {
        "lab": lab.title,
        "lab_id": lab.id,
        "generated_at": now_iso(),
        "sessions": len(data.sessions),
        "completed": ov["completed"],
        "simulated_records": simulated,
        "real_records": len(data.sessions) - simulated,
        "help_requests": len(data.help),
        "help_by_trigger": dict(Counter(h.trigger for h in data.help)),
        "median_minutes_to_complete": statistics.median(completion_minutes) if completion_minutes else None,
        "median_step_seconds": ov["median_step_seconds"],
        "checks": checks,
        "uncertain_rate_pct": round(100.0 * uncertain / checks) if checks else None,
        "quality_failures": dict(quality),
        "steps": [{k: s[k] for k in ("step_id", "title", "students_attempted", "first_try_pass_pct", "median_attempts",
                                      "uncertain_rate_pct", "top_errors")} for s in ov["insights"]],
        "top_errors": [{"error_id": e, "label": data.lab.error_label(e), "count": n} for e, n in errors.most_common(6)],
        "follow_up": follow_up[:10],
    }


def render_markdown(text: str) -> str:
    """Markdown → HTML with raw HTML disabled (model output is never trusted as markup)."""
    md = markdown.Markdown(extensions=["tables", "sane_lists"])
    md.preprocessors.deregister("html_block")
    md.inlinePatterns.deregister("html")
    return md.convert(text)


def ensure_simulated_first_line(text: str, simulated: bool) -> str:
    if not simulated:
        return text
    first = next((line for line in text.splitlines() if line.strip()), "")
    if "simulat" in first.lower():
        return text
    return f"{SIMULATED_NOTE}\n\n{text}"


def generate_report(rt: Any, lab_id: str) -> dict[str, Any]:
    """Aggregate → ``deep`` model (thinking allowed, falls back to ``reasoning``) → store → rendered payload."""
    lab = rt.labs.get(lab_id)
    if lab is None:
        raise ValueError(f"Unknown lab: {lab_id}")
    data = ClassData(rt.db, lab)
    stats = class_stats(data)
    t0 = time.perf_counter()
    res = rt.router.call("deep", [{"role": "system", "content": CLASS_REPORT_SYSTEM},
                                  {"role": "user", "content": json.dumps(stats, ensure_ascii=False)}],
                         thinking=True, max_tokens=2500, interactive=False)
    text = ensure_simulated_first_line(res.text.strip() or "_The model returned an empty report._",
                                       stats["simulated_records"] > 0)
    report = Report(id=new_id(), lab_id=lab.id, created_at=now_iso(), model_id=res.model_id, markdown=text,
                    input_stats_json=json.dumps(stats), cost_usd=res.cost_usd)
    rt.db.add_report(report)
    return report_payload(report, latency_ms=int((time.perf_counter() - t0) * 1000), fallback_from=res.fallback_from,
                          tokens=sum(res.usage.values()))


def report_payload(report: Report, latency_ms: int | None = None, fallback_from: str | None = None,
                   tokens: int | None = None) -> dict[str, Any]:
    return {"id": report.id, "lab_id": report.lab_id, "created_at": report.created_at, "model_id": report.model_id,
            "markdown": report.markdown, "html": render_markdown(report.markdown), "cost_usd": report.cost_usd,
            "latency_ms": latency_ms, "fallback_from": fallback_from, "tokens": tokens,
            "title": html.escape(f"Class report · {report.created_at[:16]}")}
