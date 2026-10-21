"""Simulated class for demonstrating the TA dashboard: ``python -m polarity seed-demo --students 28``.

Every record is written with ``is_simulated=1`` and the dashboard shows a banner whenever any exists. Never
present these numbers as real results. ``--clear`` removes them.

Targets (BUILD_PROMPT.md 12.3): first-try pass s1 85%, s2 70%, s3 55%, s4 50%, s5 80%, s6 75%, with the named
dominant mistakes; about 8% of attempts CAN'T TELL; 4–6 help requests with canned summaries marked simulated;
timestamps spread over a 90-minute class ending now, so some students are still working.
"""

from __future__ import annotations

import json
import random
from datetime import datetime, timedelta
from typing import Any

from polarity.models.lab import LabDefinition
from polarity.models.session import Attempt
from polarity.storage.db import Database, new_id

FIRST_TRY = {"s1": 0.85, "s2": 0.70, "s3": 0.55, "s4": 0.50, "s5": 0.80, "s6": 0.75}
ERROR_WEIGHTS = {
    "s1": {"E_RAILS_SWAPPED": 6, "E_LEAD_IN_STRIP": 2, "E_SAME_RAIL": 1},
    "s2": {"E_RES_SHORTED": 6, "E_RES_IN_MINUS": 2, "E_RES_BOTH_IN_STRIPS": 2},
    "s3": {"E_LED_REVERSED": 8, "E_LED_SAME_STRIP": 2, "E_LED_NOT_CONNECTED": 1},
    "s4": {"E_BTN_NOT_STRADDLING": 5, "E_BTN_ROTATED": 4, "E_BTN_WRONG_STRIP": 1},
    "s5": {"E_GND_TO_PLUS": 3, "E_GND_WRONG_STRIP": 2},
    "s6": {"E_NO_LIGHT": 1},
}
BUILD_MINUTES = {"s1": 4.0, "s2": 6.0, "s3": 8.0, "s4": 9.0, "s5": 6.0, "s6": 4.0}
UNCERTAIN_RATE = 0.08
CLASS_MINUTES = 90
ALIASES = ["Kestrel", "Maple", "Quokka", "Nimbus", "Pebble", "Juniper", "Orbit", "Cobalt", "Fern", "Pixel", "Saffron",
           "Tango", "Willow", "Basil", "Comet", "Delta", "Echo", "Flint", "Gecko", "Harbor", "Indigo", "Jade", "Koi",
           "Lumen", "Mango", "Nova", "Olive", "Pico", "Quartz", "Rook", "Sable", "Tide"]
CANNED = {
    "fix_count": ("[simulated] Three FIX verdicts on {step}; the same mistake ({err}) was flagged each time.",
                  "Repeated {err_label}.", "Point to the strip numbers on the board and ask the student to trace the path.",
                  "medium"),
    "uncertain_streak": ("[simulated] Three CAN'T TELL results in a row on {step}; photos were dark or blocked by hands.",
                         "Lighting or hands in frame, not the circuit.", "Adjust the lamp and show where to hold the board.",
                         "low"),
    "power_test": ("[simulated] Power test failed twice; the LED stayed dark both times.",
                   "An earlier step is likely wrong (often the LED orientation).", "Run the board check with the student, then inspect the LED.",
                   "high"),
    "call_ta": ("[simulated] Student pressed Call TA on {step} after {n} checks.", "Student asked for help directly.",
                "Stop by the bench and ask what is unclear.", "medium"),
}


def _verdict(step: Any, status: str, err: str | None, hint: int, conf: float) -> str:
    checks = []
    bad = set(step.error(err).related_checks) if err and step.error(err) else set()
    for c in step.checks:
        if status == "uncertain":
            res = "not_visible"
        elif c.id in bad:
            res = "fail"
        else:
            res = "pass"
        checks.append({"id": c.id, "result": res, "observation": "[simulated]"})
    perception = {"step_id": step.id, "checks": checks, "detected_error_ids": [err] if err else [], "confidence": conf,
                  "spoken_feedback": "[simulated]", "evidence_region": None, "retake_instruction": None,
                  "student_answer": None, "parts_seen": []}
    reason = {"pass": "model:pass", "fix": f"model:fail {','.join(sorted(bad)) or 'x'}"}.get(status, "quality:dark")
    return json.dumps({"status": status, "reason": reason, "perception": perception if status != "uncertain" else None,
                       "model_id": "SIMULATED", "step_id": step.id, "hint_level": hint})


def seed_class(db: Database, lab: LabDefinition, students: int = 28, seed: int = 10,
               now: datetime | None = None) -> dict[str, Any]:
    """Write a believable simulated class. Returns counts."""
    rng = random.Random(seed)
    now = now or datetime.now().astimezone()
    start = now - timedelta(minutes=CLASS_MINUTES)
    aliases = ALIASES[:]
    rng.shuffle(aliases)
    help_made: list[tuple[str, str, str, datetime]] = []
    counts = {"sessions": 0, "attempts": 0, "help": 0, "completed": 0}
    with db.transaction():
        for i in range(students):
            alias = aliases[i % len(aliases)] + ("" if i < len(aliases) else f"-{i}")
            t = start + timedelta(minutes=rng.uniform(0, 55))
            session = db.create_session(alias, lab.id, f"B{i + 1:02d}", started_at=t.isoformat(timespec="seconds"),
                                        is_simulated=True)
            counts["sessions"] += 1
            finished = True
            for step in lab.steps:
                t += timedelta(minutes=rng.lognormvariate(0, 0.35) * BUILD_MINUTES.get(step.id, 5.0))
                if t > now:
                    finished = False
                    break
                first_try = rng.random() < FIRST_TRY.get(step.id, 0.7)
                fixes = 0 if first_try else rng.choices([1, 2, 3, 4], weights=[60, 25, 10, 5])[0]
                weights = ERROR_WEIGHTS.get(step.id) or {e.id: 1 for e in step.common_errors}
                hint = 1
                fix_done = 0
                plan = ["fix"] * fixes + ["pass"]
                stopped = False
                for status in plan:
                    while rng.random() < UNCERTAIN_RATE:  # a retake before a decisive verdict
                        db.add_attempt(Attempt(id=new_id(), session_id=session.id, step_id=step.id, kind="check",
                                               status="uncertain", reason="quality:dark", hint_level=hint,
                                               verdict_json=_verdict(step, "uncertain", None, hint, 0.0),
                                               model_id=None, latency_ms=0, created_at=t.isoformat(timespec="seconds"),
                                               is_simulated=True))
                        counts["attempts"] += 1
                        t += timedelta(seconds=rng.uniform(20, 60))
                    if t > now:
                        stopped = True
                        break
                    err = rng.choices(list(weights), weights=list(weights.values()))[0] if status == "fix" else None
                    conf = round(rng.uniform(0.8, 0.95), 2)
                    db.add_attempt(Attempt(id=new_id(), session_id=session.id, step_id=step.id, kind="check",
                                           status=status, reason="led:lit" if status == "pass" and step.led_check else
                                           ("model:pass" if status == "pass" else "model:fail"), confidence=conf,
                                           hint_level=hint, verdict_json=_verdict(step, status, err, hint, conf),
                                           model_id="SIMULATED", latency_ms=int(rng.uniform(1400, 3600)),
                                           created_at=t.isoformat(timespec="seconds"), is_simulated=True))
                    counts["attempts"] += 1
                    if status == "fix":
                        hint = min(3, hint + 1)
                        fix_done += 1
                        threshold = 2 if step.led_check else 3  # same escalation rules as the live engine
                        if fix_done == threshold and len(help_made) < 6 and not any(h[0] == session.id for h in help_made):
                            help_made.append((session.id, step.id, "power_test" if step.led_check else "fix_count", t))
                        t += timedelta(minutes=rng.uniform(1.0, 3.5))
                        if t > now:
                            stopped = True
                            break
                if stopped:
                    finished = False
                    break
            if finished:
                db.complete_session(session.id, t.isoformat(timespec="seconds"))
                counts["completed"] += 1
        # Make sure the queue shows 4–6 requests: add "Call TA" from students who are still working.
        open_sessions = [s for s in db.list_sessions(lab.id) if s.is_simulated and not s.completed_at
                         and not any(h[0] == s.id for h in help_made)]
        rng.shuffle(open_sessions)
        for s in open_sessions:
            if len(help_made) >= 4:
                break
            atts = [a for a in db.list_attempts(s.id) if a.kind == "check"]
            step_id = atts[-1].step_id if atts else lab.steps[0].id
            help_made.append((s.id, step_id, "call_ta", now - timedelta(minutes=rng.uniform(1, 12))))
        for n, (sid, step_id, trigger, at) in enumerate(help_made[:6]):
            step = lab.step(step_id)
            atts = [a for a in db.list_attempts(sid, step_id) if a.kind == "check"]
            errs = [e for a in atts for e in (json.loads(a.verdict_json or "{}").get("perception") or {}).get("detected_error_ids", [])]
            err = errs[-1] if errs else None
            text, cause, action, urgency = CANNED[trigger]
            summary = {"summary_for_ta": text.format(step=step.title if step else step_id, err=err or "–", n=len(atts)),
                       "likely_root_cause": cause.format(err_label=(lab.error_label(err) if err else "mistake").rstrip(".")),
                       "suggested_ta_action": action, "urgency": urgency, "simulated": True}
            resolved = n % 3 == 2  # a few were already handled earlier in the class
            db.add_help(sid, step_id, trigger, summary=summary, created_at=at.isoformat(timespec="seconds"),
                        is_simulated=True, status="resolved" if resolved else "open",
                        resolved_at=(at + timedelta(minutes=4)).isoformat(timespec="seconds") if resolved else None)
            counts["help"] += 1
    return counts
