"""SessionEngine: the deterministic state machine that drives a bench session (BUILD_PROMPT.md 4.3 step 8, 12.1).

pass / pass_partial → advance (last step → session completed); fix → fix count and hint level go up (max 3);
uncertain → stay on the step and show the retake instruction. After every result the escalation rules run:
≥3 FIX on a step, 3 CAN'T TELL in a row, 2 failed power tests, a safety redirect, or "Call TA" create a help
request (deduplicated per session and step) and notify the TA dashboard.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from typing import Any

from polarity.engine.verifier import CheckRequest
from polarity.models.lab import LabDefinition, Step
from polarity.models.session import Attempt, HelpRequest, Session, SessionState, StepProgress
from polarity.models.verdict import FinalVerdict
from polarity.storage.db import new_id, now_iso

log = logging.getLogger(__name__)

TRIGGER_PRIORITY = ("safety", "power_test", "fix_count", "uncertain_streak", "call_ta")
_CALL_TA = re.compile(r"\b(call|ask|get|tell)\s+(the|your|a)\s+(TA|teaching assistant|instructor|lab assistant)\b", re.I)
_OFF = re.compile(r"\b(switch|turn|power|unplug)\w*\b[^.]{0,30}?\boff\b|\bunplug\b|\bdisconnect\b", re.I)
_HAZARD = re.compile(r"\b(smoke|smoking|burn\w*|hot|heat\w*|mains|fire|spark\w*|melt\w*|swollen|leak\w*|shock)\b", re.I)


def is_safety_redirect(text: str | None) -> bool:
    """True when the model told the student to stop and get the TA (switch off / hazard + call the TA)."""
    if not text:
        return False
    return bool(_CALL_TA.search(text)) and bool(_OFF.search(text) or _HAZARD.search(text))


class EngineError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class SessionEngine:
    """One active bench session. Thread-safe; one check or ask at a time."""

    def __init__(self, rt: Any) -> None:
        self.rt = rt
        self._lock = threading.RLock()
        self._busy = threading.Lock()
        self.session: Session | None = None
        self.lab: LabDefinition | None = None
        self.index = 0
        self.completed = False
        self.progress: dict[str, StepProgress] = {}
        self.baselines: dict[str, Any] = {}
        self.baseline_pending: str | None = None
        self.last_verdict: FinalVerdict | None = None
        self.started_monotonic = 0.0

    # ── lifecycle ────────────────────────────────────────────────────────────────────────────

    def start(self, alias: str, lab_id: str, bench_id: str | None = None) -> SessionState:
        alias = (alias or "").strip()[:40]
        if not alias:
            raise EngineError("bad_alias", "Please enter a nickname.")
        lab = self.rt.labs.get(lab_id)
        if lab is None:
            raise EngineError("unknown_lab", f"Unknown lab: {lab_id}")
        with self._lock:
            self.session = self.rt.db.create_session(alias, lab.id, bench_id or self.rt.config.bench_id)
            self.lab = lab
            self.index = 0
            self.completed = False
            self.progress = {s.id: StepProgress(step_id=s.id) for s in lab.steps}
            self.baselines = {}
            self.last_verdict = None
            self.started_monotonic = time.monotonic()
            self._prepare_step(lab.steps[0])
        self.rt.hub_send("session", self.session.model_dump())
        state = self.state()
        self.rt.bus.publish("session_started", state)
        return state  # type: ignore[return-value]

    def reset(self) -> None:
        with self._lock:
            self.session = None
            self.lab = None
            self.progress = {}
            self.baselines = {}
            self.completed = False
            self.last_verdict = None
        self.rt.bus.publish("session_reset", None)

    @property
    def current_step(self) -> Step | None:
        if self.lab is None or self.completed or self.index >= len(self.lab.steps):
            return None
        return self.lab.steps[self.index]

    def state(self) -> SessionState | None:
        with self._lock:
            if self.session is None or self.lab is None:
                return None
            step = self.current_step
            open_help = [self.rt.help_payload(h) for h in self.rt.db.list_help("open", session_id=self.session.id)]
            return SessionState(
                session=self.session, lab_id=self.lab.id, lab_title=self.lab.title, current_index=self.index,
                current_step_id=step.id if step else None, completed=self.completed,
                progress=[self.progress[s.id] for s in self.lab.steps],
                total_checks=sum(p.checks for p in self.progress.values()),
                elapsed_s=int(time.monotonic() - self.started_monotonic), open_help=open_help)

    def _require(self) -> tuple[Session, LabDefinition, Step]:
        if self.session is None or self.lab is None:
            raise EngineError("no_session", "Start a session first.")
        step = self.current_step
        if step is None:
            raise EngineError("completed", "This lab is already complete.")
        return self.session, self.lab, step

    # ── step preparation, LED baseline, demo staging ─────────────────────────────────────────

    def _prepare_step(self, step: Step) -> None:
        cam = self.rt.camera
        if getattr(cam, "source_name", "") == "demo" and self.lab is not None:
            idx = self.lab.step_index(step.id)
            # Show the board as it looks when this step begins: the previous step done correctly.
            scene = (self.lab.steps[idx - 1].id, "correct") if idx > 0 else (step.id, "_empty")
            cam.set_scene(*scene)
            self.rt.bus.publish("demo_scene", {"step": scene[0], "label": scene[1]})
        if step.led_check is not None:
            if not self.set_baseline(step.id):
                self.baseline_pending = step.id  # the edge monitor fills it from the next good frame

    def set_baseline(self, step_id: str | None = None) -> bool:
        """Store the current warped frame as the LED baseline for ``step_id`` (default: current step)."""
        step_id = step_id or (self.current_step.id if self.current_step else None)
        if step_id is None:
            return False
        frame = self.rt.camera.latest()
        if frame is None:
            return False
        _, warped, quality = self.rt.verifier.analyse(frame.image, self.rt.camera.motion.value)
        if warped is None or not quality.ok:
            return False
        with self._lock:
            self.baselines[step_id] = warped
            if self.baseline_pending == step_id:
                self.baseline_pending = None
        self.rt.bus.publish("baseline_set", {"step_id": step_id})
        return True

    def offer_baseline(self, warped: Any, quality_ok: bool) -> None:
        """Called by the edge monitor with each analysed frame while a baseline is pending."""
        step_id = self.baseline_pending
        if step_id and quality_ok and warped is not None:
            with self._lock:
                if self.baseline_pending == step_id:
                    self.baselines[step_id] = warped
                    self.baseline_pending = None
            self.rt.bus.publish("baseline_set", {"step_id": step_id, "auto": True})

    # ── check ────────────────────────────────────────────────────────────────────────────────

    def check(self, audio_wav: bytes | None = None, typed_question: str | None = None) -> dict[str, Any]:
        if not self._busy.acquire(blocking=False):
            raise EngineError("busy", "A check is already running.")
        try:
            return self._check(audio_wav, typed_question)
        finally:
            self._busy.release()

    def _check(self, audio_wav: bytes | None, typed_question: str | None) -> dict[str, Any]:
        session, lab, step = self._require()
        prog = self.progress[step.id]
        frame = self.rt.camera.sharpest_recent(1.0)
        if frame is None:
            raise EngineError("no_camera", "The camera isn't sending pictures. Check the cable, then try again.")
        self.rt.bus.publish("check_started", {"step_id": step.id})
        mock_hint = frame.label.split("/", 1)[1] if frame.label and "/" in frame.label else None
        req = CheckRequest(lab=lab, step=step, frame=frame.image, hint_level=prog.hint_level,
                           typed_question=(typed_question or None), audio_wav=audio_wav,
                           motion=self.rt.camera.motion.value, led_baseline=self.baselines.get(step.id),
                           session_id=session.id, mock_hint=mock_hint)
        outcome = self.rt.verifier.check(req)
        final = outcome.final
        attempt_id = new_id()
        final.attempt_id = attempt_id
        raw_path = self.rt.media.save_image(session.id, f"{attempt_id}_raw.jpg", outcome.raw)
        warped_path = self.rt.media.save_image(session.id, f"{attempt_id}_warped.jpg", outcome.warped) \
            if outcome.warped is not None else None
        audio_path = self.rt.media.save_bytes(session.id, f"{attempt_id}.wav", audio_wav) if audio_wav else None
        final.warped_url = f"/media/{warped_path}" if warped_path else None
        attempt = Attempt(id=attempt_id, session_id=session.id, step_id=step.id, kind="check", status=final.status,
                          reason=final.reason, confidence=final.perception.confidence if final.perception else None,
                          hint_level=prog.hint_level, verdict_json=final.model_dump_json(),
                          led_json=json.dumps(final.led) if final.led else None, raw_image_path=raw_path,
                          warped_image_path=warped_path, audio_path=audio_path, model_id=final.model_id,
                          latency_ms=final.latency_ms, cost_usd=final.cost_usd, created_at=now_iso())
        self.rt.db.add_attempt(attempt)
        self.rt.hub_send("attempt", attempt.model_dump(), thumb=outcome.warped)
        advanced, help_req = self._apply(step, prog, final)
        self.last_verdict = final
        state = self.state()
        payload = {"verdict": final.model_dump(mode="json"), "state": state.model_dump(mode="json") if state else None,
                   "advanced": advanced, "completed": self.completed,
                   "help": self.rt.help_payload(help_req) if help_req else None, "transcript": outcome.transcript}
        self.rt.bus.publish("check_result", payload)
        if advanced and self.current_step is not None:
            self.rt.bus.publish("step_advanced", {"step_id": self.current_step.id})
        if self.completed:
            self.rt.bus.publish("session_completed", payload["state"])
        return payload

    def _apply(self, step: Step, prog: StepProgress, final: FinalVerdict) -> tuple[bool, HelpRequest | None]:
        """State machine transition + escalation rules."""
        with self._lock:
            prog.checks += 1
            advanced = False
            if final.status in ("pass", "pass_partial"):
                prog.passed = True
                prog.uncertain_streak = 0
                self._advance()
                advanced = True
            elif final.status == "fix":
                prog.fix_count += 1
                prog.uncertain_streak = 0
                prog.hint_level = min(3, prog.hint_level + 1)
                if step.led_check is not None:
                    prog.power_test_fails += 1
            else:
                prog.uncertain_streak += 1
            help_req = None if advanced else self._escalate(step, prog, final)
            if advanced and final.perception and is_safety_redirect(final.perception.student_answer):
                help_req = self._create_help(step, "safety")
            return advanced, help_req

    def _advance(self) -> None:
        assert self.lab is not None and self.session is not None
        self.index += 1
        if self.index >= len(self.lab.steps):
            self.completed = True
            self.rt.db.complete_session(self.session.id)
            self.session = self.rt.db.get_session(self.session.id) or self.session
            self.rt.hub_send("session", self.session.model_dump())
        else:
            self._prepare_step(self.lab.steps[self.index])

    def _escalate(self, step: Step, prog: StepProgress, final: FinalVerdict | None) -> HelpRequest | None:
        esc = self.rt.config.settings.escalation
        triggers = []
        answer = final.perception.student_answer if final and final.perception else None
        if is_safety_redirect(answer):
            triggers.append("safety")
        if step.led_check is not None and prog.power_test_fails >= esc.power_test_fails:
            triggers.append("power_test")
        if prog.fix_count >= esc.fix_count:
            triggers.append("fix_count")
        if prog.uncertain_streak >= esc.uncertain_streak:
            triggers.append("uncertain_streak")
        if not triggers:
            return None
        trigger = min(triggers, key=TRIGGER_PRIORITY.index)
        return self._create_help(step, trigger)

    def _create_help(self, step: Step, trigger: str) -> HelpRequest | None:
        assert self.session is not None
        existing = [h for h in self.rt.db.list_help("open", session_id=self.session.id) if h.step_id == step.id]
        if existing:
            return None  # already escalated for this step; the TA card is still open
        help_req = self.rt.db.add_help(self.session.id, step.id, trigger)
        self.rt.bus.publish("help_created", self.rt.help_payload(help_req))
        self.rt.on_help_created(help_req)
        return help_req

    # ── other actions ────────────────────────────────────────────────────────────────────────

    def call_ta(self) -> dict[str, Any]:
        session, _, step = self._require()
        help_req = self._create_help(step, "call_ta")
        if help_req is None:
            existing = [h for h in self.rt.db.list_help("open", session_id=session.id) if h.step_id == step.id]
            return {"created": False, "help": self.rt.help_payload(existing[0]) if existing else None}
        return {"created": True, "help": self.rt.help_payload(help_req)}

    def ask(self, audio_wav: bytes | None, question: str | None) -> dict[str, Any]:
        if not self._busy.acquire(blocking=False):
            raise EngineError("busy", "Still working on the last request.")
        try:
            from polarity.engine.voice_qa import answer_question

            session, lab, step = self._require()
            result = answer_question(self.rt, session, lab, step, audio_wav, question)
            if result.get("safety"):
                help_req = self._create_help(step, "safety")
                result["help"] = self.rt.help_payload(help_req) if help_req else None
            return result
        finally:
            self._busy.release()

    def skip_step(self, by: str = "ta") -> SessionState | None:
        session, _, step = self._require()
        attempt = Attempt(id=new_id(), session_id=session.id, step_id=step.id, kind="ta_skip", status="skipped",
                          reason=f"skipped by {by}", created_at=now_iso())
        self.rt.db.add_attempt(attempt)
        with self._lock:
            self.progress[step.id].passed = True
            self._advance()
        if self.current_step is not None:
            self.rt.bus.publish("step_advanced", {"step_id": self.current_step.id, "skipped": True})
        elif self.completed:
            self.rt.bus.publish("session_completed", self.state())
        return self.state()

    def goto_step(self, step_id: str) -> SessionState | None:
        """Go back to an earlier step (board audit "Go to step N")."""
        session, lab, current = self._require()
        target = lab.step_index(step_id)
        if target > self.index:
            raise EngineError("bad_step", "You can only go back to an earlier step.")
        with self._lock:
            for s in lab.steps[target:]:
                self.progress[s.id].passed = False
            self.index = target
            self._prepare_step(lab.steps[target])
        self.rt.bus.publish("step_advanced", {"step_id": step_id, "back": True})
        return self.state()
