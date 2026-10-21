"""FastAPI app factory: pages, JSON API, MJPEG stream, media and the WebSocket event feed."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import cv2
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from polarity import __version__
from polarity.audio import AudioError, validate_wav
from polarity.config import APP_NAME, TAGLINE
from polarity.edge.quality import RETAKE_INSTRUCTIONS
from polarity.engine import analytics
from polarity.engine.session_engine import EngineError
from polarity.llm.router import BudgetExceeded, InvalidModelOutput, ModelCallFailed, ModelUnavailable
from polarity.runtime import Runtime

log = logging.getLogger(__name__)
WEB_DIR = Path(__file__).resolve().parent
TA_COOKIE = "polarity_ta"
ICON_DIR = WEB_DIR / "static" / "img" / "icons"
ICON_NAMES = sorted(p.stem for p in ICON_DIR.glob("*.svg"))
_ICON_CACHE: dict[str, str] = {}


def icon(name: str, cls: str = "icon") -> Markup:
    """Inline SVG icon (currentColor) so status colours and themes apply to it."""
    if name not in _ICON_CACHE:
        path = ICON_DIR / f"{name}.svg"
        _ICON_CACHE[name] = path.read_text(encoding="utf-8").strip() if path.exists() else ""
    svg = _ICON_CACHE[name]
    return Markup(svg.replace("<svg ", f'<svg class="{cls}" ', 1)) if svg else Markup("")

ENGINE_STATUS = {"no_session": 409, "completed": 409, "busy": 409, "bad_alias": 422, "unknown_lab": 404,
                 "no_camera": 503, "empty_question": 422, "bad_step": 422, "bad_image": 422}


class StartBody(BaseModel):
    student_alias: str = Field(min_length=1, max_length=40)
    lab_id: str | None = None
    bench_id: str | None = Field(default=None, max_length=20)


class PinBody(BaseModel):
    pin: str


class SceneBody(BaseModel):
    step: str
    label: str


class GotoBody(BaseModel):
    step_id: str


class ThresholdBody(BaseModel):
    section: str
    key: str
    value: float


class BudgetBody(BaseModel):
    session_usd: float | None = None
    day_usd: float | None = None


class LatencyBody(BaseModel):
    ms: int = Field(ge=0, le=120_000)


class ReportBody(BaseModel):
    lab_id: str | None = None


class PartBody(BaseModel):
    part: str = Field(min_length=2, max_length=24)


class LabSaveBody(BaseModel):
    lab: dict[str, Any]
    publish: bool = False


class HubIngestBody(BaseModel):
    kind: str
    bench_id: str | None = None
    payload: dict[str, Any]
    thumb_b64: str | None = None


class SeedBody(BaseModel):
    students: int = Field(default=28, ge=1, le=60)
    seed: int = 10
    lab_id: str | None = None


def create_app(runtime: Runtime | None = None) -> FastAPI:
    rt = runtime or Runtime()
    secret = secrets.token_bytes(16)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        rt.bus.attach_loop(asyncio.get_running_loop())
        rt.start()
        try:
            yield
        finally:
            rt.stop()

    app = FastAPI(title=APP_NAME, version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.rt = rt
    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")

    # ── errors → friendly JSON ───────────────────────────────────────────────────────────────

    @app.exception_handler(EngineError)
    async def _engine_error(_: Request, exc: EngineError) -> JSONResponse:
        return JSONResponse({"error": exc.code, "message": str(exc)}, status_code=ENGINE_STATUS.get(exc.code, 400))

    @app.exception_handler(BudgetExceeded)
    async def _budget(_: Request, exc: BudgetExceeded) -> JSONResponse:
        return JSONResponse({"error": "budget", "message": f"{exc}. Ask your TA to raise the budget.",
                             "scope": exc.scope, "spent": exc.spent, "limit": exc.limit}, status_code=429)

    @app.exception_handler(ModelUnavailable)
    async def _unavailable(_: Request, exc: ModelUnavailable) -> JSONResponse:
        return JSONResponse({"error": "model_unavailable", "message": str(exc)}, status_code=503)

    @app.exception_handler(ModelCallFailed)
    async def _failed(_: Request, exc: ModelCallFailed) -> JSONResponse:
        return JSONResponse({"error": "model_failed", "message": "I couldn't check that right now — try again.",
                             "detail": str(exc)}, status_code=502)

    @app.exception_handler(InvalidModelOutput)
    async def _invalid(_: Request, exc: InvalidModelOutput) -> JSONResponse:
        return JSONResponse({"error": "model_invalid", "message": "The model's answer was unreadable — try again."},
                            status_code=502)

    @app.exception_handler(AudioError)
    async def _audio(_: Request, exc: AudioError) -> JSONResponse:
        return JSONResponse({"error": "bad_audio", "message": str(exc)}, status_code=422)

    # ── TA PIN ───────────────────────────────────────────────────────────────────────────────

    def _pin() -> str:
        return rt.config.env.ta_pin.get_secret_value()

    def _token() -> str:
        return hmac.new(secret, _pin().encode("utf-8"), hashlib.sha256).hexdigest()

    def is_ta(request: Request) -> bool:
        header = request.headers.get("x-ta-pin")
        if header is not None and secrets.compare_digest(header.encode("utf-8"), _pin().encode("utf-8")):
            return True
        cookie = request.cookies.get(TA_COOKIE)
        return cookie is not None and secrets.compare_digest(cookie, _token())

    def require_ta(request: Request) -> None:
        if not is_ta(request):
            raise HTTPException(status_code=401, detail="TA PIN required")

    app.state.is_ta = is_ta
    app.state.require_ta = require_ta

    @app.post("/api/ta/login")
    def ta_login(body: PinBody) -> JSONResponse:
        if not secrets.compare_digest(body.pin.encode("utf-8"), _pin().encode("utf-8")):
            return JSONResponse({"error": "bad_pin", "message": "Wrong PIN."}, status_code=401)
        resp = JSONResponse({"ok": True})
        resp.set_cookie(TA_COOKIE, _token(), httponly=True, samesite="strict", max_age=12 * 3600)
        return resp

    @app.post("/api/ta/logout")
    def ta_logout() -> JSONResponse:
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(TA_COOKIE)
        return resp

    # ── system ───────────────────────────────────────────────────────────────────────────────

    def safe_config() -> dict[str, Any]:
        cfg = rt.config
        s = cfg.settings
        return {
            "app_name": APP_NAME, "tagline": TAGLINE, "version": __version__, "mock": cfg.mock,
            "camera_source": cfg.env.camera_source, "markers_enabled": cfg.env.markers_enabled,
            "audio_mode": cfg.audio_mode(), "audio_variant": cfg.capabilities.audio_input.variant,
            "default_lab": cfg.env.default_lab, "labs": rt.labs.list(), "theme": s.ui.theme,
            "speak_feedback": s.ui.speak_feedback, "audio_max_seconds": s.audio.max_seconds,
            "budget": {"session_usd": cfg.env.budget_session_usd, "day_usd": cfg.env.budget_day_usd,
                       "pricing_known": bool(cfg.prices)},
            "routing": cfg.routing_table(), "capabilities_verified": cfg.capabilities.verified,
            "has_key": bool(cfg.api_key), "tavily_enabled": bool(cfg.tavily_key), "role": cfg.role_override,
            "bench_id": cfg.bench_id, "retention_days": cfg.env.media_retention_days,
            "check_timeout_s": s.timeouts_s.perception,
            "retake_instructions": RETAKE_INSTRUCTIONS,
        }

    app.state.safe_config = safe_config

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "app": APP_NAME, "version": __version__, "mock": rt.config.mock,
                "camera": rt.camera.status(), "role": rt.config.role_override}

    @app.get("/api/capabilities")
    def capabilities() -> dict[str, Any]:
        return rt.config.capabilities.model_dump(mode="json")

    @app.get("/api/config")
    def config_route() -> dict[str, Any]:
        return safe_config()

    # ── session ──────────────────────────────────────────────────────────────────────────────

    @app.post("/api/session/start")
    def session_start(body: StartBody) -> dict[str, Any]:
        state = rt.engine.start(body.student_alias, body.lab_id or rt.config.env.default_lab, body.bench_id)
        return {"state": state.model_dump(mode="json")}

    @app.get("/api/session/current")
    def session_current() -> dict[str, Any]:
        state = rt.engine.state()
        lab = rt.engine.lab
        return {"state": state.model_dump(mode="json") if state else None,
                "lab": lab.model_dump(mode="json") if lab else None,
                "last_verdict": rt.engine.last_verdict.model_dump(mode="json") if rt.engine.last_verdict else None,
                "baseline_ready": bool(rt.engine.current_step and rt.engine.current_step.id in rt.engine.baselines)}

    @app.post("/api/session/reset")
    def session_reset() -> dict[str, Any]:
        rt.engine.reset()
        return {"ok": True}

    @app.post("/api/session/goto")
    def session_goto(body: GotoBody) -> dict[str, Any]:
        state = rt.engine.goto_step(body.step_id)
        return {"state": state.model_dump(mode="json") if state else None}

    async def _read_audio(audio: UploadFile | None) -> bytes | None:
        if audio is None:
            return None
        data = await audio.read()
        if not data:
            return None
        wav, _ = validate_wav(data, rt.config.settings.audio.max_seconds)
        return wav

    @app.post("/api/check")
    async def check(audio: UploadFile | None = File(default=None),
                    typed_question: str | None = Form(default=None)) -> dict[str, Any]:
        wav = await _read_audio(audio)
        return await run_in_threadpool(rt.engine.check, wav, (typed_question or "").strip()[:500] or None)

    @app.post("/api/ask")
    async def ask(audio: UploadFile | None = File(default=None),
                  question: str | None = Form(default=None)) -> dict[str, Any]:
        wav = await _read_audio(audio)
        result = await run_in_threadpool(rt.engine.ask, wav, (question or "").strip()[:500] or None)
        rt.last_answer = result
        return result

    @app.post("/api/help")
    def call_help() -> dict[str, Any]:
        return rt.engine.call_ta()

    @app.post("/api/baseline")
    def baseline() -> dict[str, Any]:
        ok = rt.engine.set_baseline()
        return {"ok": ok, "message": None if ok else "Could not see the board clearly enough to store a baseline."}

    # ── frames and media ─────────────────────────────────────────────────────────────────────

    @app.get("/stream.mjpg")
    async def stream(request: Request, view: str = "raw", frames: int | None = None) -> StreamingResponse:
        fps = max(1.0, float(rt.config.settings.camera.stream_fps))
        width = int(rt.config.settings.camera.stream_width)

        async def gen() -> AsyncIterator[bytes]:
            sent = 0
            while frames is None or sent < frames:
                if frames is None and await request.is_disconnected():
                    break
                jpg = await run_in_threadpool(rt.stream_frame, "warped" if view == "warped" else "raw", width)
                yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(jpg)).encode("ascii")
                       + b"\r\n\r\n" + jpg + b"\r\n")
                sent += 1
                await asyncio.sleep(1.0 / fps)

        return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame",
                                 headers={"Cache-Control": "no-store"})

    @app.get("/api/frame/warped.jpg")
    def warped_jpg() -> Response:
        jpg = rt.stream_frame("warped", 1024)
        return Response(jpg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.get("/api/frame/ledmask.jpg")
    def ledmask_jpg() -> Response:
        frame = rt.camera.latest()
        step = rt.engine.current_step
        if frame is None:
            raise HTTPException(404, "no frame")
        _, warped, _ = rt.verifier.analyse(frame.image)
        if warped is None:
            raise HTTPException(404, "board not found")
        baseline = rt.engine.baselines.get(step.id) if step else None
        colour = step.led_check.colour if step and step.led_check else "red"
        mask = rt.verifier.led.mask(warped, baseline, colour)
        overlay = warped.copy()
        overlay[mask > 0] = (191, 212, 45)
        ok, buf = cv2.imencode(".jpg", cv2.addWeighted(warped, 0.45, overlay, 0.55, 0))
        return Response(buf.tobytes(), media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.get("/media/{path:path}")
    def media(path: str) -> FileResponse:
        resolved = rt.media.resolve(path)
        if resolved is None:
            raise HTTPException(404, "not found")
        return FileResponse(resolved)

    # ── WebSocket ────────────────────────────────────────────────────────────────────────────

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        await websocket.accept()
        q = rt.bus.subscribe()
        state = rt.engine.state()
        await websocket.send_json({"type": "hello", "data": {
            "state": state.model_dump(mode="json") if state else None, "config": safe_config()}})

        async def pump() -> None:
            while True:
                await websocket.send_text(await q.get())

        sender = asyncio.create_task(pump())
        try:
            while True:
                await websocket.receive_text()  # pings from the client; content ignored
        except WebSocketDisconnect:
            pass
        finally:
            sender.cancel()
            rt.bus.unsubscribe(q)

    # ── TA actions ───────────────────────────────────────────────────────────────────────────

    @app.get("/api/ta/help", dependencies=[Depends(require_ta)])
    def ta_help(status: str = "open") -> dict[str, Any]:
        items = [rt.help_payload(h) for h in rt.db.list_help(None if status == "all" else status)]
        return {"items": items}

    @app.post("/api/ta/help/{help_id}/resolve", dependencies=[Depends(require_ta)])
    def ta_resolve(help_id: str) -> dict[str, Any]:
        if not rt.db.resolve_help(help_id):
            raise HTTPException(404, "No open help request with that id.")
        payload = rt.help_payload(rt.db.get_help(help_id))
        rt.bus.publish("help_resolved", payload)
        return {"ok": True, "help": payload}

    @app.post("/api/ta/step/skip", dependencies=[Depends(require_ta)])
    def ta_skip() -> dict[str, Any]:
        state = rt.engine.skip_step("ta")
        return {"state": state.model_dump(mode="json") if state else None}

    # ── demo + debug ─────────────────────────────────────────────────────────────────────────

    @app.get("/api/demo/scenes")
    def demo_scenes() -> dict[str, Any]:
        cam = rt.camera
        if getattr(cam, "source_name", "") != "demo":
            return {"enabled": False, "scenes": []}
        scenes = [{"step": s, "label": label} for (s, label) in sorted(cam.scenes())]
        return {"enabled": True, "scenes": scenes, "current": {"step": cam.scene[0], "label": cam.scene[1]}}

    @app.post("/api/demo/scene")
    def demo_scene(body: SceneBody) -> dict[str, Any]:
        cam = rt.camera
        if getattr(cam, "source_name", "") != "demo":
            raise HTTPException(409, "Demo scenes are only available with CAMERA_SOURCE=demo.")
        if not cam.set_scene(body.step, body.label):
            raise HTTPException(404, "Unknown scene.")
        rt.bus.publish("demo_scene", {"step": body.step, "label": body.label})
        return {"ok": True}

    @app.get("/api/debug/state")
    def debug_state() -> dict[str, Any]:
        sess = rt.engine.session
        spent_session, spent_day = rt.db.spend(sess.id if sess else None)
        return {
            "capabilities": rt.config.capabilities.model_dump(mode="json"), "routing": rt.config.routing_table(),
            "calls": rt.db.recent_model_calls(20), "tokens": rt.db.token_totals(),
            "last_verdict": rt.engine.last_verdict.model_dump(mode="json") if rt.engine.last_verdict else None,
            "last_answer": rt.last_answer,
            "budget": {"session_usd": spent_session, "day_usd": spent_day, "limit_session": rt.config.env.budget_session_usd,
                       "limit_day": rt.config.env.budget_day_usd, "pricing_known": bool(rt.config.prices)},
            "thresholds": {"quality": rt.config.settings.quality.model_dump(), "led": rt.config.settings.led.model_dump(),
                           "decision": rt.config.settings.decision.model_dump()},
            "json_mode_effective": rt.router.effective_json_mode(), "mock_latency_ms": rt.config.env.polarity_mock_latency_ms,
            "baselines": sorted(rt.engine.baselines), "baseline_pending": rt.engine.baseline_pending,
        }

    @app.post("/api/debug/thresholds", dependencies=[Depends(require_ta)])
    def debug_thresholds(body: ThresholdBody) -> dict[str, Any]:
        section = getattr(rt.config.settings, body.section, None)
        if section is None or body.section not in ("quality", "led", "decision") or not hasattr(section, body.key):
            raise HTTPException(422, "Unknown threshold.")
        current = getattr(section, body.key)
        if not isinstance(current, (int, float)) or isinstance(current, bool):
            raise HTTPException(422, "Only numeric thresholds can be changed here.")
        setattr(section, body.key, type(current)(body.value))
        return {"ok": True, "note": "Session-only change; edit config/settings.yaml to keep it."}

    @app.post("/api/debug/budget", dependencies=[Depends(require_ta)])
    def debug_budget(body: BudgetBody) -> dict[str, Any]:
        if body.session_usd is not None:
            rt.config.env.budget_session_usd = body.session_usd
        if body.day_usd is not None:
            rt.config.env.budget_day_usd = body.day_usd
        return {"ok": True, "budget": {"session_usd": rt.config.env.budget_session_usd,
                                       "day_usd": rt.config.env.budget_day_usd}}

    @app.post("/api/debug/mock_latency", dependencies=[Depends(require_ta)])
    def debug_mock_latency(body: LatencyBody) -> dict[str, Any]:
        if not rt.config.mock:
            raise HTTPException(409, "Only available in mock mode.")
        rt.config.env.polarity_mock_latency_ms = body.ms
        return {"ok": True}

    # ── pages ────────────────────────────────────────────────────────────────────────────────

    templates = Jinja2Templates(directory=WEB_DIR / "templates")
    templates.env.globals.update(icon=icon, icon_names=ICON_NAMES)

    def page(request: Request, name: str, page_id: str, title: str, **extra: Any) -> HTMLResponse:
        boot = {"config": safe_config(), "page": page_id, **extra.pop("boot", {})}
        ctx = {"app_name": APP_NAME, "tagline": TAGLINE, "mock": rt.config.mock, "page": page_id, "title": title,
               "theme": rt.config.settings.ui.theme, "boot": boot, **extra}
        return templates.TemplateResponse(request, name, ctx)

    @app.get("/", response_class=HTMLResponse)
    def start_page(request: Request) -> HTMLResponse:
        return page(request, "start.html", "start", "Start")

    @app.get("/bench", response_class=HTMLResponse, response_model=None)
    def bench_page(request: Request) -> HTMLResponse | RedirectResponse:
        if rt.engine.session is None:
            return RedirectResponse("/", status_code=303)
        return page(request, "bench.html", "bench", "Bench")

    @app.get("/ta", response_class=HTMLResponse)
    def ta_page(request: Request) -> HTMLResponse:
        if not is_ta(request):
            return page(request, "pin.html", "pin", "TA sign-in", gate_title="TA dashboard")
        return page(request, "ta.html", "ta", "TA dashboard")

    @app.get("/debug", response_class=HTMLResponse)
    def debug_page(request: Request) -> HTMLResponse:
        return page(request, "debug.html", "debug", "Debug", boot={"is_ta": is_ta(request)})

    @app.get("/assets/print/{name}")
    def print_asset(name: str) -> FileResponse:
        if name not in ("marker_mat_A4.pdf", "marker_mat_A4.png"):
            raise HTTPException(404, "not found")
        path = rt.config.paths.root / "assets" / "print" / name
        if not path.exists():
            from polarity.edge.markers import write_mat

            write_mat(path.parent, APP_NAME)
        return FileResponse(path, filename=name)

    # ── TA analytics ─────────────────────────────────────────────────────────────────────────

    def _class_data(lab_id: str | None) -> analytics.ClassData:
        ids = analytics.labs_with_sessions(rt.db)
        chosen = lab_id or (rt.engine.lab.id if rt.engine.lab else None) or (ids[0] if ids else rt.config.env.default_lab)
        lab = rt.labs.get(chosen)
        if lab is None:
            raise HTTPException(404, "Unknown lab.")
        return analytics.ClassData(rt.db, lab)

    @app.get("/api/ta/overview", dependencies=[Depends(require_ta)])
    def ta_overview(lab_id: str | None = None) -> dict[str, Any]:
        data = _class_data(lab_id)
        out = analytics.overview(data)
        out["labs_with_data"] = analytics.labs_with_sessions(rt.db)
        return out

    @app.get("/api/ta/heatmap", dependencies=[Depends(require_ta)])
    def ta_heatmap(lab_id: str | None = None) -> dict[str, Any]:
        return analytics.heatmap(_class_data(lab_id))

    @app.get("/api/ta/session/{session_id}/timeline", dependencies=[Depends(require_ta)])
    def ta_timeline(session_id: str, step_id: str | None = None) -> dict[str, Any]:
        session = rt.db.get_session(session_id)
        if session is None:
            raise HTTPException(404, "Unknown session.")
        lab = rt.labs.get(session.lab_id)
        return {"session": session.model_dump(), "items": analytics.timeline(rt.db, lab, session_id, step_id)}

    # ── TA intelligence: class report + seeded demo class ────────────────────────────────────

    @app.post("/api/ta/report", dependencies=[Depends(require_ta)])
    def ta_report(body: ReportBody) -> dict[str, Any]:
        from polarity.engine.report import generate_report

        lab_id = body.lab_id or (rt.engine.lab.id if rt.engine.lab else None) or \
            (analytics.labs_with_sessions(rt.db) or [rt.config.env.default_lab])[0]
        try:
            return generate_report(rt, lab_id)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/ta/reports", dependencies=[Depends(require_ta)])
    def ta_reports() -> dict[str, Any]:
        return {"items": [{"id": r.id, "lab_id": r.lab_id, "created_at": r.created_at, "model_id": r.model_id}
                          for r in rt.db.list_reports()]}

    @app.get("/api/ta/report/{report_id}.md", dependencies=[Depends(require_ta)])
    def ta_report_md(report_id: str) -> Response:
        report = rt.db.get_report(report_id)
        if report is None:
            raise HTTPException(404, "Unknown report.")
        return Response(report.markdown, media_type="text/markdown; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="class-report-{report_id[:8]}.md"'})

    @app.get("/api/ta/report/{report_id}", dependencies=[Depends(require_ta)])
    def ta_report_get(report_id: str) -> dict[str, Any]:
        from polarity.engine.report import report_payload

        report = rt.db.get_report(report_id)
        if report is None:
            raise HTTPException(404, "Unknown report.")
        return report_payload(report)

    @app.post("/api/demo/seed", dependencies=[Depends(require_ta)])
    def demo_seed(body: SeedBody) -> dict[str, Any]:
        from polarity.demo.seed import seed_class

        lab = rt.labs.get(body.lab_id or rt.config.env.default_lab)
        if lab is None:
            raise HTTPException(404, "Unknown lab.")
        counts = seed_class(rt.db, lab, body.students, body.seed)
        rt.bus.publish("hub_update", {"seeded": counts})
        return counts

    @app.delete("/api/demo/seed", dependencies=[Depends(require_ta)])
    def demo_seed_clear() -> dict[str, Any]:
        removed = rt.db.clear_simulated()
        rt.bus.publish("hub_update", {"cleared": removed})
        return {"removed_sessions": removed}

    # ── P1: board audit, part lookup, lab editor + compiler, hub ingest ─────────────────────────

    @app.post("/api/audit")
    def board_audit() -> dict[str, Any]:
        from polarity.engine.board_audit import run_audit

        return run_audit(rt)

    @app.post("/api/parts/lookup")
    def parts_lookup(body: PartBody) -> JSONResponse:
        from polarity.engine.parts import PartsUnavailable, lookup

        try:
            return JSONResponse(lookup(rt, body.part))
        except PartsUnavailable as exc:
            return JSONResponse({"error": "parts_unavailable", "message": str(exc)}, status_code=503)
        except ValueError as exc:
            return JSONResponse({"error": "bad_part", "message": str(exc)}, status_code=422)

    @app.get("/labs/editor", response_class=HTMLResponse)
    def editor_page(request: Request) -> HTMLResponse:
        if not is_ta(request):
            return page(request, "pin.html", "pin", "TA sign-in", gate_title="Lab editor")
        return page(request, "editor.html", "editor", "Lab editor")

    @app.get("/api/labs")
    def labs_list() -> dict[str, Any]:
        return {"items": rt.labs.list()}

    @app.get("/api/labs/{lab_id}")
    def labs_get(lab_id: str) -> dict[str, Any]:
        lab = rt.labs.get(lab_id)
        if lab is None:
            raise HTTPException(404, "Unknown lab.")
        published = (rt.config.paths.labs / f"{lab_id}.yaml").exists()
        return {"lab": lab.model_dump(mode="json"), "source": "published" if published else "draft"}

    @app.put("/api/labs/{lab_id}", dependencies=[Depends(require_ta)])
    def labs_put(lab_id: str, body: LabSaveBody) -> JSONResponse:
        from polarity.engine.lab_compiler import validate_lab

        lab, errors = validate_lab(body.lab)
        if lab is None:
            return JSONResponse({"error": "invalid_lab", "message": errors}, status_code=422)
        if not lab.id.replace("_", "").replace("-", "").isalnum():
            return JSONResponse({"error": "invalid_lab", "message": "id: use letters, digits, _ or -"}, status_code=422)
        path = rt.labs.save(lab, publish=body.publish)
        if lab.id != lab_id and body.publish:
            stale = rt.config.paths.drafts / f"{lab_id}.yaml"
            if stale.exists():
                stale.unlink()
        rt.bus.publish("labs_changed", {"lab_id": lab.id, "published": body.publish})
        return JSONResponse({"ok": True, "lab_id": lab.id, "published": body.publish, "path": path.name})

    @app.post("/api/labs/compile", dependencies=[Depends(require_ta)])
    async def labs_compile(files: list[UploadFile] | None = File(default=None), upload_id: str | None = Form(default=None),
                           confirm: bool = Form(default=False), sample: bool = Form(default=False)) -> JSONResponse:
        from polarity.engine import lab_compiler as lc

        try:
            if upload_id is None:
                if sample:
                    path = rt.config.paths.labs / "samples" / "lab1_handout.pdf"
                    if not path.exists():
                        path = rt.config.paths.root / "labs" / "samples" / "lab1_handout.pdf"
                    items = [(path.name, path.read_bytes())]
                else:
                    items = [(f.filename or "upload", await f.read()) for f in (files or [])]
                upload = await run_in_threadpool(lc.create_upload, rt.config.paths.media, items)
            else:
                upload = lc.load_upload(rt.config.paths.media, upload_id)
        except lc.CompileError as exc:
            return JSONResponse({"error": "compile", "message": str(exc)}, status_code=422)
        pages = [f"/media/compile/{upload.id}/{p.name}" for p in upload.pages]
        if not confirm:
            return JSONResponse({"upload_id": upload.id, "pages": pages, "estimate": lc.estimate(rt.config, len(pages))})

        def work() -> None:
            try:
                result = lc.compile_upload(rt, upload, progress=lambda p: rt.bus.publish("compile_progress", {**p, "upload_id": upload.id}))
                rt.bus.publish("compile_done", {"upload_id": upload.id, **result})
            except Exception as exc:  # noqa: BLE001 - reported to the editor, never crashes the server
                log.exception("lab compile failed")
                rt.bus.publish("compile_failed", {"upload_id": upload.id, "message": str(exc)})

        import threading

        threading.Thread(target=work, name="lab-compile", daemon=True).start()
        return JSONResponse({"upload_id": upload.id, "pages": pages, "started": True})

    @app.post("/api/hub/ingest", dependencies=[Depends(require_ta)])
    def hub_ingest(body: HubIngestBody) -> dict[str, Any]:
        import base64
        import json as _json

        import numpy as np

        from polarity.models.session import Attempt, HelpRequest, Session

        if rt.config.role_override != "hub":
            raise HTTPException(409, "This server is not running with --role hub.")
        if body.kind == "session":
            s = Session.model_validate(body.payload)
            rt.db.create_session(s.student_alias, s.lab_id, s.bench_id or body.bench_id, session_id=s.id,
                                 started_at=s.started_at, is_simulated=s.is_simulated)
            if s.completed_at:
                rt.db.complete_session(s.id, s.completed_at)
        elif body.kind == "attempt":
            a = Attempt.model_validate(body.payload)
            thumb = None
            if body.thumb_b64:
                data = np.frombuffer(base64.b64decode(body.thumb_b64), np.uint8)
                img = cv2.imdecode(data, cv2.IMREAD_COLOR)
                if img is not None:
                    thumb = rt.media.save_image(a.session_id, f"{a.id}_warped.jpg", img)
            rt.db.add_attempt(a.model_copy(update={"raw_image_path": None, "audio_path": None, "warped_image_path": thumb}))
        elif body.kind == "help":
            h = HelpRequest.model_validate(body.payload)
            rt.db.add_help(h.session_id, h.step_id, h.trigger, help_id=h.id, created_at=h.created_at,
                           summary=_json.loads(h.summary_json) if h.summary_json else None, status=h.status,
                           resolved_at=h.resolved_at, is_simulated=h.is_simulated)
            rt.bus.publish("help_created" if h.status == "open" else "help_updated", rt.help_payload(rt.db.get_help(h.id)))
        else:
            raise HTTPException(422, "Unknown record kind.")
        rt.bus.publish("hub_update", {"kind": body.kind, "bench_id": body.bench_id})
        return {"ok": True}

    @app.get("/api/hub/status")
    def hub_status() -> dict[str, Any]:
        client = rt.hub_client
        return {"role": rt.config.role_override, "hub_url": rt.config.hub_url,
                "pending": client.pending() if client else 0, "sent": client.sent if client else 0,
                "last_error": client.last_error if client else None}

    return app
