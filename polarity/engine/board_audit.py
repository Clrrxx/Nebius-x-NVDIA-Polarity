"""Whole-board "bug hunt" (BUILD_PROMPT.md 13.3, P1): after a failed power test (or on a TA button press),
Nemotron Nano Omni evaluates every step's checks on the current image and ranks the most likely culprits.
"""

from __future__ import annotations

import json
from typing import Any

from polarity.engine.verifier import encode_jpeg
from polarity.llm import prompts
from polarity.models.session import Attempt
from polarity.models.verdict import BoardAudit
from polarity.storage.db import new_id, now_iso


def run_audit(rt: Any) -> dict[str, Any]:
    from polarity.engine.session_engine import EngineError

    engine = rt.engine
    if engine.session is None or engine.lab is None:
        raise EngineError("no_session", "Start a session first.")
    frame = rt.camera.sharpest_recent(1.0)
    if frame is None:
        raise EngineError("no_camera", "The camera isn't sending pictures.")
    _, warped, quality = rt.verifier.analyse(frame.image, rt.camera.motion.value)
    if warped is None or not quality.ok:
        from polarity.edge.quality import retake_for

        raise EngineError("bad_image", retake_for(quality) or "I can't see the whole board clearly.")
    image = encode_jpeg(warped, rt.config.settings.images.max_long_side, rt.config.settings.images.jpeg_quality)
    mock_hint = frame.label.split("/", 1)[1] if frame.label and "/" in frame.label else None
    res = rt.router.call("perception", prompts.audit_messages(engine.lab, image), schema=BoardAudit, max_tokens=900,
                         session_id=engine.session.id, mock_hint=mock_hint)
    audit: BoardAudit = res.parsed  # type: ignore[assignment]
    valid = {s.id: {c.id for c in s.checks} for s in engine.lab.steps}
    suspects = [s for s in audit.suspects if s.step_id in valid and s.check_id in valid[s.step_id]]
    suspects.sort(key=lambda s: -s.confidence)
    step_id = engine.current_step.id if engine.current_step else engine.lab.steps[-1].id
    path = rt.media.save_image(engine.session.id, f"audit_{new_id()}_warped.jpg", warped)
    rt.db.add_attempt(Attempt(id=new_id(), session_id=engine.session.id, step_id=step_id, kind="audit",
                              status="answered", reason="audit",
                              verdict_json=json.dumps({"suspects": [s.model_dump() for s in suspects],
                                                       "spoken_feedback": audit.spoken_feedback}),
                              warped_image_path=path, model_id=res.model_id, latency_ms=res.latency_ms,
                              cost_usd=res.cost_usd, created_at=now_iso()))
    return {"suspects": [s.model_dump() for s in suspects[:3]], "spoken_feedback": audit.spoken_feedback,
            "model_id": res.model_id, "latency_ms": res.latency_ms, "warped_url": f"/media/{path}"}
