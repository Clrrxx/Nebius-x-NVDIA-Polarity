"""Voice / typed Q&A about the current step (BUILD_PROMPT.md 9.5.2).

The answer comes from Nemotron Nano Omni with the current top-down board image, so it is grounded in what the
student actually built. Audio handling follows the AUDIO_MODE verified in Phase 0:
``omni_combined`` sends the clip in the same request; ``omni_separate`` transcribes it first; ``browser_stt`` and
``typed`` receive text from the browser. Intent classification runs on the cheap ``fast_text`` model in parallel.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from polarity.engine.verifier import encode_jpeg
from polarity.llm import prompts
from polarity.llm.router import RouterError
from polarity.models.lab import LabDefinition, Step
from polarity.models.session import Attempt, Session
from polarity.models.verdict import AudioTranscript, IntentLabel, ShortText, VoiceAnswer
from polarity.storage.db import new_id, now_iso

PART_RE = re.compile(r"\b[A-Z]{1,4}\d{2,5}[A-Z]?\b")


def find_part_numbers(*texts: str | None) -> list[str]:
    """Printed part numbers (e.g. NE555, LM7805) mentioned in any of ``texts``."""
    seen: dict[str, None] = {}
    for text in texts:
        for match in PART_RE.findall((text or "").upper()):
            seen.setdefault(match, None)
    return list(seen)


def classify_intent(rt: Any, question: str, session_id: str | None) -> IntentLabel | None:
    try:
        res = rt.router.call("fast_text", [{"role": "system", "content": prompts.INTENT_SYSTEM},
                                           {"role": "user", "content": json.dumps({"question": question})}],
                             schema=IntentLabel, max_tokens=120, session_id=session_id)
        return res.parsed  # type: ignore[return-value]
    except RouterError:
        return None


def answer_question(rt: Any, session: Session, lab: LabDefinition, step: Step, audio_wav: bytes | None,
                    question: str | None) -> dict[str, Any]:
    from polarity.engine.session_engine import EngineError, is_safety_redirect

    cfg = rt.config
    mode = cfg.audio_mode()
    variant = cfg.capabilities.audio_input.variant or "input_audio"
    image = None
    frame = rt.camera.latest()
    if frame is not None:
        _, warped, _ = rt.verifier.analyse(frame.image, rt.camera.motion.value)
        image = encode_jpeg(warped if warped is not None else frame.image, cfg.settings.images.max_long_side,
                            cfg.settings.images.jpeg_quality)
    text_q = (question or "").strip() or None
    transcript = None
    if audio_wav and mode == "omni_separate" and not cfg.mock:
        res = rt.router.call("perception", prompts.transcribe_messages(audio_wav, variant), schema=AudioTranscript,
                             max_tokens=200, session_id=session.id)
        transcript = res.parsed.transcript if res.parsed else None  # type: ignore[union-attr]
        text_q = " ".join(t for t in (text_q, transcript) if t) or None
    audio_for_call = audio_wav if audio_wav and (mode == "omni_combined" or cfg.mock) else None
    if not text_q and not audio_for_call:
        raise EngineError("empty_question", "I didn't catch a question. Try again, or type it.")

    messages = prompts.voice_qa_messages(lab, step, image, text_q, audio_for_call, variant if audio_for_call else None)
    with ThreadPoolExecutor(max_workers=1) as pool:
        intent_future = pool.submit(classify_intent, rt, text_q, session.id) if text_q else None
        res = rt.router.call("perception", messages, schema=VoiceAnswer, max_tokens=500, session_id=session.id)
        intent = intent_future.result() if intent_future else None
    ans: VoiceAnswer = res.parsed  # type: ignore[assignment]
    answer = ans.answer
    if len(answer.split()) > 40:
        try:
            short = rt.router.call("fast_text", [{"role": "system", "content": prompts.shorten_system(40)},
                                                 {"role": "user", "content": json.dumps({"max_words": 40, "text": answer})}],
                                   schema=ShortText, max_tokens=200, session_id=session.id)
            answer = short.parsed.text if short.parsed else answer  # type: ignore[union-attr]
        except RouterError:
            answer = " ".join(answer.split()[:40])
    parts = find_part_numbers(text_q, " ".join(ans.parts_mentioned), intent.part_number if intent else None)
    final_intent = intent.intent if intent else ans.intent
    safety = is_safety_redirect(answer)
    attempt = Attempt(id=new_id(), session_id=session.id, step_id=step.id, kind="ask", status="answered",
                      reason=f"intent:{final_intent}",
                      verdict_json=json.dumps({"question": text_q, "transcript": transcript, "answer": answer,
                                               "intent": final_intent, "parts": parts}),
                      audio_path=rt.media.save_bytes(session.id, f"ask_{new_id()}.wav", audio_wav) if audio_wav else None,
                      model_id=res.model_id, latency_ms=res.latency_ms, cost_usd=res.cost_usd, created_at=now_iso())
    rt.db.add_attempt(attempt)
    payload = {"answer": answer, "intent": final_intent, "parts": parts, "question": text_q, "transcript": transcript,
               "model_id": res.model_id, "latency_ms": res.latency_ms, "safety": safety}
    rt.bus.publish("answer", payload)
    return payload
