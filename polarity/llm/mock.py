"""Canned model responses. Active ONLY when ``POLARITY_MOCK_MODELS=1`` (the UI then shows an amber
"MOCK MODE: not real AI output" badge on every screen and every call is logged with ``model_id="MOCK"``).

Perception verdicts are keyed by the demo scene label (``correct``, an error id such as ``E_LED_REVERSED``, or a
special scene such as ``_hand``/``_partial``) so the whole UI flow can be shown without hardware or credits.
Hints come from the TA-authored lab YAML. Nothing here is used for accuracy claims, and nothing here invents web
sources or statistics: the mock report only restates numbers present in its input.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel

from polarity.models.lab import LabDefinition, load_lab

PART_RE = re.compile(r"\b[A-Z]{1,4}\d{2,5}[A-Z]?\b")
SAFETY_WORDS = ("smoke", "smoking", "burn", "burning", "hot", "mains", "melt", "swollen", "fire", "spark")

_lab_cache: dict[str, LabDefinition] = {}


def _lab(config: Any, lab_id: str | None) -> LabDefinition | None:
    if not lab_id:
        return None
    if lab_id not in _lab_cache:
        path = config.paths.labs / f"{lab_id}.yaml"
        if not path.exists():
            return None
        _lab_cache[lab_id] = load_lab(path)
    return _lab_cache[lab_id]


def _system_text(messages: list[dict[str, Any]]) -> str:
    return "\n".join(str(m.get("content")) for m in messages if m.get("role") == "system")


def _user_parts(messages: list[dict[str, Any]]) -> tuple[str, set[str]]:
    text, kinds = "", set()
    for m in messages:
        if m.get("role") not in ("user", "tool"):
            continue
        content = m.get("content")
        if isinstance(content, str):
            text += content + "\n"
        elif isinstance(content, list):
            for part in content:
                kinds.add(part.get("type", ""))
                if part.get("type") == "text":
                    text += part.get("text", "") + "\n"
    return text, kinds


def _first_json(text: str) -> dict[str, Any]:
    from polarity.llm.jsonio import extract_json

    return extract_json(text) or {}


def canned_answer(question: str | None, has_audio: bool) -> tuple[str, str, list[str]]:
    """Keyword-based canned answer: (answer, intent, parts_mentioned)."""
    q = (question or "").lower()
    if not q and has_audio:
        return ("Mock mode received your voice clip, but transcription needs the real model on Token Factory. "
                "Try typing the question instead.", "other", [])
    if any(w in q for w in SAFETY_WORDS):
        return "Switch the power off now and call your TA before touching anything.", "help", []
    parts = PART_RE.findall(question or "")
    if parts:
        return (f"{parts[0]} is a printed part number. Tap the part chip to look up its pinout from the web.",
                "part_info", parts)
    if "leg" in q and ("long" in q or "short" in q or "which" in q):
        return ("The longer leg is the LED's + side (anode). It goes in the resistor's strip; the short leg sits by "
                "the flat edge of the rim.", "how_to", ["LED"])
    if "resistor" in q or "band" in q:
        return ("The resistor limits the current so the LED doesn't burn out. Brown-black-brown means 100 ohms.",
                "why", ["resistor"])
    if "button" in q:
        return ("Put the button across the centre gap so two legs sit above it and two below, one pair in the LED's "
                "short-leg strip.", "how_to", ["push button"])
    if "rail" in q or "red line" in q or "blue line" in q:
        return "The long rows along the edge are the rails: red line is +, blue line is −.", "how_to", []
    if "help" in q or "stuck" in q or "ta" in q.split():
        return "Press Call TA and your TA will come over. Meanwhile, compare your board with the step picture.", "help", []
    return ("Good question. Look at the step picture and compare each leg's strip with your board, then press "
            "Check.", "other", [])


def _verdict(payload: dict[str, Any], label: str | None, second_look: bool, lab: LabDefinition | None,
             has_audio: bool) -> dict[str, Any]:
    step_info = payload.get("step") or {}
    step = lab.step(step_info.get("id", "")) if lab else None
    checks = payload.get("checks") or [{"id": c.id, "statement": c.statement} for c in (step.checks if step else [])]
    hint_level = int(payload.get("hint_level") or 1)
    label = label or "correct"
    results, detected, retake = [], [], None
    err = step.error(label) if (step and label.startswith("E_")) else None
    confidence = 0.92
    if label == "_hand":
        results = [{"id": c["id"], "result": "not_visible", "observation": "[mock] A hand covers this part of the board."}
                   for c in checks]
        retake = "Move your hands out of the frame, then press Check again."
        confidence = 0.35
    elif err is not None:
        bad = set(err.related_checks) or {checks[0]["id"]}
        results = [{"id": c["id"], "result": "fail" if c["id"] in bad else "pass",
                    "observation": f"[mock] {err.visual_cue}" if c["id"] in bad else "[mock] Matches this demo scene."}
                   for c in checks]
        detected = [err.id]
        confidence = 0.86
    else:
        partial = label == "_partial"
        for c in checks:
            hard = bool(step and (chk := step.check(c["id"])) and chk.allow_uncertain)
            if partial and hard:
                results.append({"id": c["id"], "result": "not_visible",
                                "observation": "[mock] This detail is in shadow, so it can't be confirmed from above."})
            else:
                results.append({"id": c["id"], "result": "pass", "observation": "[mock] Matches this demo scene."})
        if partial:
            retake = "Tilt the lamp so the LED rim is lit, then check again if you want to confirm it."
            confidence = 0.82
        elif step is not None and step.id == "s4":
            confidence = 0.78  # inside the grey zone, so the demo shows the second look
    if second_look:
        confidence = max(confidence, 0.9) if label != "_hand" else confidence
    nxt = payload.get("next_step_title")
    if err is not None:
        spoken = err.hint(hint_level)
    elif label == "_hand":
        spoken = "I can't see the board clearly. Move your hands away and check again."
    elif label == "_partial":
        spoken = "Everything I can see looks right. One detail is hidden — double-check it yourself."
    else:
        spoken = f"Nice work, that looks right. Next up: {nxt}." if nxt else "Nice work, that looks right."
    answer = None
    question = payload.get("typed_question")
    if question or has_audio:
        answer = canned_answer(question, has_audio)[0]
    region = {"x": 0.30, "y": 0.18, "w": 0.30, "h": 0.40} if err is not None else None
    return {"step_id": step_info.get("id", ""), "checks": results, "detected_error_ids": detected,
            "confidence": round(confidence, 2), "evidence_region": region, "retake_instruction": retake,
            "spoken_feedback": spoken, "student_answer": answer, "parts_seen": []}


def _report(payload: dict[str, Any]) -> str:
    """Template report that only restates numbers present in the input statistics."""
    lines = ["MOCK MODE — not real AI output. This report was filled in from a template, not written by Nemotron."]
    if payload.get("simulated_records"):
        lines.append(f"Includes simulated class data ({payload['simulated_records']} simulated sessions).")
    lines += ["", "## Snapshot",
              f"- Sessions: {payload.get('sessions', 0)}, completed: {payload.get('completed', 0)}, "
              f"help requests: {payload.get('help_requests', 0)}"]
    steps = payload.get("steps") or []
    ranked = sorted(steps, key=lambda s: (s.get("first_try_pass_pct") is None, s.get("first_try_pass_pct") or 0))
    lines += ["", "## Where the class got stuck"]
    for s in ranked[:3]:
        lines.append(f"- {s.get('step_id')} {s.get('title', '')}: first-try pass {s.get('first_try_pass_pct')}%, "
                     f"median attempts {s.get('median_attempts')}")
    lines += ["", "## Most common mistakes"]
    for e in (payload.get("top_errors") or [])[:5]:
        lines.append(f"- {e.get('error_id')} ({e.get('label', '')}): {e.get('count')}")
    lines += ["", "## Students who may need follow-up"]
    for f in (payload.get("follow_up") or [])[:6]:
        lines.append(f"- {f.get('alias')}: {f.get('reason')}")
    lines += ["", "## Suggested re-teach for next session",
              "- (mock) Re-demonstrate the step with the lowest first-try pass rate above.",
              "- (mock) Show one correct and one incorrect board side by side for the most common mistake.",
              "", "## Data caveats",
              f"- Uncertain rate: {payload.get('uncertain_rate_pct')}%; quality-gate retakes: {payload.get('quality_failures')}."]
    return "\n".join(lines)


def respond(role: str, messages: list[dict[str, Any]], schema: type[BaseModel] | None,
            tools: list[dict[str, Any]] | None, hint: str | None, config: Any) -> tuple[str, list[dict[str, Any]]]:
    """Return ``(text, tool_calls)`` for a mocked call."""
    system = _system_text(messages)
    user_text, kinds = _user_parts(messages)
    payload = _first_json(user_text)
    name = schema.__name__ if schema else ""
    has_audio = bool(kinds & {"input_audio", "audio_url"})
    lab = _lab(config, payload.get("lab"))

    if name == "PerceptionVerdict":
        return json.dumps(_verdict(payload, hint, "second, closer look" in system, lab, has_audio)), []
    if name == "VoiceAnswer":
        answer, intent, parts = canned_answer(payload.get("question"), has_audio)
        return json.dumps({"answer": answer, "intent": intent, "parts_mentioned": parts}), []
    if name == "AudioTranscript":
        return json.dumps({"transcript": "", "intent": "other"}), []
    if name == "IntentLabel":
        q = payload.get("question") or user_text
        _, intent, parts = canned_answer(q, False)
        return json.dumps({"intent": intent, "part_number": parts[0] if parts else None}), []
    if name == "ShortText":
        text = payload.get("text") or user_text
        limit = int(payload.get("max_words") or 25)
        head = re.split(r"\s+[—–-]\s+|;\s+", text, maxsplit=1)[0].rstrip(" ,.")  # cut at a clause boundary
        if len(head.split()) <= limit and head != text:
            return json.dumps({"text": head + "."}), []
        words = text.split()
        return json.dumps({"text": " ".join(words[:limit]) + ("…" if len(words) > limit else "")}), []
    if name == "Diagnosis":
        fixes = payload.get("fix_count", 0)
        top = payload.get("top_error") or "no specific error id"
        trigger = payload.get("trigger", "")
        urgency = "high" if trigger in ("safety", "power_test") else ("medium" if fixes >= 3 else "low")
        return json.dumps({
            "summary_for_ta": f"[mock] {payload.get('alias', 'Student')} has {fixes} FIX verdicts on "
                              f"{payload.get('step_title', payload.get('step_id', 'this step'))}; most frequent: {top}.",
            "likely_root_cause": f"[mock] Repeated {top}.",
            "suggested_ta_action": "[mock] Look at the latest photo with the student and point to the strip involved.",
            "urgency": urgency}), []
    if name == "BoardAudit":
        suspects = []
        if lab and hint and hint.startswith("E_"):
            for s in lab.steps:
                err = s.error(hint)
                if err and err.related_checks:
                    suspects.append({"step_id": s.id, "check_id": err.related_checks[0],
                                     "why": f"[mock] {err.visual_cue}", "confidence": 0.7})
        if not suspects:
            suspects = [{"step_id": "s3", "check_id": "c_orientation",
                         "why": "[mock] The LED's flat edge is hard to see; it may be reversed.", "confidence": 0.5},
                        {"step_id": "s4", "check_id": "c_btn_rotation",
                         "why": "[mock] The button may be rotated.", "confidence": 0.3}]
        first = suspects[0]["step_id"]
        return json.dumps({"suspects": suspects,
                           "spoken_feedback": f"Let's go back to step {first[1:]} and check it closely."}), []
    if name == "PartSummary":
        results = payload.get("results") or []
        urls = [r.get("url") for r in results if r.get("url")]
        summary = ("MOCK MODE: no model summary was generated. "
                   + (f"{len(urls)} real search results are listed as sources." if urls
                      else "No search results were available."))
        return json.dumps({"summary": summary, "pinout": [], "sources": urls}), []
    if name == "PageExtract":
        return json.dumps({"page_summary": "[mock] Handout page with a push-button LED build.",
                           "components": ["breadboard", "battery holder", "red LED", "100 ohm resistor",
                                          "push button", "jumper wires"],
                           "steps_found": [{"title": s.title, "instruction": s.instruction, "figure_description": None}
                                           for s in (_lab(config, "lab1").steps if _lab(config, "lab1") else [])]}), []
    if name == "LabDefinition":
        base = _lab(config, "lab1")
        if base is None:
            return "{}", []
        data = base.model_dump(mode="json")
        data.update({"id": "lab_compiled_mock", "title": "MOCK: compiled push-button LED lab", "ai_drafted": True,
                     "version": "0.1"})
        return json.dumps(data), []
    if role == "deep" or "end-of-class report" in system:
        return _report(payload), []
    if tools:
        part = (PART_RE.findall(user_text) or ["NE555"])[0]
        return "", [{"id": "mock_call_1", "type": "function",
                     "function": {"name": "lookup_part", "arguments": json.dumps({"part_number": part})}}]
    return "MOCK MODE response.", []
