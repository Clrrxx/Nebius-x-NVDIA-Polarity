"""HTTP + WebSocket API in mock/demo mode: a full session from start to completion, plus every guard rail."""

from __future__ import annotations

import io
import wave

import numpy as np
from fastapi.testclient import TestClient

PIN = {"X-TA-PIN": "2468"}


def wav_bytes(seconds: float = 1.0, rate: int = 16000, channels: int = 1) -> bytes:
    t = np.arange(int(seconds * rate)) / rate
    tone = (0.2 * np.sin(2 * np.pi * 220 * t) * 32767).astype("<i2")
    if channels == 2:
        tone = np.repeat(tone, 2)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(tone.tobytes())
    return buf.getvalue()


def scene(c: TestClient, step: str, label: str) -> None:
    assert c.post("/api/demo/scene", json={"step": step, "label": label}).status_code == 200


def check(c: TestClient, **files) -> dict:  # noqa: ANN003
    r = c.post("/api/check", files=files or None, data={})
    assert r.status_code == 200, r.text
    return r.json()


def test_system_endpoints_expose_no_secrets(client: TestClient) -> None:
    assert client.get("/api/health").json()["mock"] is True
    cfg = client.get("/api/config").json()
    text = str(cfg)
    assert cfg["app_name"] == "Polarity" and cfg["mock"] is True and "2468" not in text
    assert {r["role"] for r in cfg["routing"]} == {"perception", "fast_text", "reasoning", "deep"}
    assert "json_mode" in client.get("/api/capabilities").json()


def test_full_session_happy_path_with_events(client: TestClient) -> None:
    with client.websocket_connect("/ws") as ws:
        assert ws.receive_json()["type"] == "hello"
        r = client.post("/api/session/start", json={"student_alias": "Robin", "lab_id": "lab1", "bench_id": "B07"})
        assert r.status_code == 200 and r.json()["state"]["current_step_id"] == "s1"
        assert client.get("/api/demo/scenes").json()["current"] == {"step": "s1", "label": "_empty"}
        steps = ["s1", "s2", "s3", "s4", "s5", "s6"]
        for i, step in enumerate(steps):
            scene(client, step, "correct")
            body = check(client)
            assert body["verdict"]["status"] == "pass", (step, body["verdict"])
            assert body["advanced"] is True
            if i + 1 < len(steps):
                assert body["state"]["current_step_id"] == steps[i + 1]
        assert body["completed"] is True and body["verdict"]["reason"] == "led:lit"
        assert body["state"]["completed"] is True and body["state"]["total_checks"] == 6
        seen = set()
        for _ in range(200):
            msg = ws.receive_json()
            seen.add(msg["type"])
            if msg["type"] == "session_completed":
                break
        assert {"check_started", "check_result", "step_advanced", "session_completed"} <= seen
    calls = client.get("/api/debug/state").json()["calls"]
    assert calls and all(c["model_id"] == "MOCK" for c in calls)


def test_fix_hint_ladder_and_escalation(client: TestClient) -> None:
    client.post("/api/session/start", json={"student_alias": "Sam", "lab_id": "lab1"})
    for step in ("s1", "s2"):
        scene(client, step, "correct")
        check(client)
    scene(client, "s3", "E_LED_REVERSED")
    levels, help_seen = [], None
    for _ in range(3):
        body = check(client)
        assert body["verdict"]["status"] == "fix"
        levels.append(body["verdict"]["hint_level"])
        help_seen = body["help"] or help_seen
    assert levels == [1, 2, 3]
    assert body["verdict"]["hint_text"].startswith("Pull the LED out")  # level-3 hint = exact fix
    assert help_seen and help_seen["trigger"] == "fix_count" and help_seen["alias"] == "Sam"
    assert client.get("/api/ta/help").status_code == 401  # PIN required
    items = client.get("/api/ta/help", headers=PIN).json()["items"]
    assert len(items) == 1 and items[0]["thumb"].startswith("/media/")
    assert client.get(items[0]["thumb"]).headers["content-type"] == "image/jpeg"
    assert client.post(f"/api/ta/help/{items[0]['id']}/resolve", headers=PIN).json()["ok"] is True
    assert client.get("/api/ta/help", headers=PIN).json()["items"] == []


def test_ta_cookie_login(client: TestClient) -> None:
    assert client.post("/api/ta/login", json={"pin": "0000"}).status_code == 401
    assert client.post("/api/ta/login", json={"pin": "2468"}).status_code == 200
    assert client.get("/api/ta/help").status_code == 200  # cookie now set


def test_quality_failure_is_local_and_free(client: TestClient) -> None:
    client.post("/api/session/start", json={"student_alias": "Ana", "lab_id": "lab1"})
    scene(client, "s1", "_dark")
    body = check(client)
    v = body["verdict"]
    assert v["status"] == "uncertain" and v["reason"] == "quality:dark" and "dark" in v["retake_instruction"]
    assert v["model_id"] is None and client.get("/api/debug/state").json()["calls"] == []
    assert body["state"]["current_step_id"] == "s1"


def test_cant_tell_streak_escalates(client: TestClient) -> None:
    client.post("/api/session/start", json={"student_alias": "Lee", "lab_id": "lab1"})
    scene(client, "s1", "_hand")
    triggers = [check(client)["help"] for _ in range(3)]
    assert triggers[:2] == [None, None] and triggers[2]["trigger"] == "uncertain_streak"


def test_call_ta_is_deduplicated(client: TestClient) -> None:
    client.post("/api/session/start", json={"student_alias": "Kai", "lab_id": "lab1"})
    first = client.post("/api/help").json()
    second = client.post("/api/help").json()
    assert first["created"] is True and second["created"] is False
    assert second["help"]["id"] == first["help"]["id"]


def test_audio_upload_validation(client: TestClient) -> None:
    client.post("/api/session/start", json={"student_alias": "Ivy", "lab_id": "lab1"})
    ok = client.post("/api/ask", files={"audio": ("q.wav", wav_bytes(1.0, 44100, 2), "audio/wav")})
    assert ok.status_code == 200 and "transcription needs the real model" in ok.json()["answer"]
    too_long = client.post("/api/ask", files={"audio": ("q.wav", wav_bytes(20.0), "audio/wav")})
    assert too_long.status_code == 422 and too_long.json()["error"] == "bad_audio"
    not_wav = client.post("/api/ask", files={"audio": ("q.mp3", b"ID3not-a-wav-file" * 20, "audio/mpeg")})
    assert not_wav.status_code == 422
    scene(client, "s1", "correct")
    body = check(client, audio=("q.wav", wav_bytes(1.0), "audio/wav"))
    assert body["verdict"]["status"] == "pass" and body["verdict"]["perception"]["student_answer"]


def test_typed_question_and_safety_redirect(client: TestClient) -> None:
    client.post("/api/session/start", json={"student_alias": "Mo", "lab_id": "lab1"})
    r = client.post("/api/ask", data={"question": "Which leg of the LED is longer?"})
    assert r.status_code == 200 and "longer leg" in r.json()["answer"]
    r2 = client.post("/api/ask", data={"question": "The resistor is smoking and hot, what do I do?"})
    body = r2.json()
    assert body["safety"] is True and body["help"]["trigger"] == "safety"
    r3 = client.post("/api/ask", data={"question": "What is an NE555?"})
    assert r3.json()["parts"] == ["NE555"]
    assert client.post("/api/ask", data={}).status_code == 422


def test_budget_exceeded_is_reported(client: TestClient) -> None:
    client.post("/api/session/start", json={"student_alias": "Bo", "lab_id": "lab1"})
    assert client.post("/api/debug/budget", json={"day_usd": 0}).status_code == 401  # TA PIN required
    client.post("/api/debug/budget", json={"day_usd": 0}, headers=PIN)
    scene(client, "s1", "correct")
    r = client.post("/api/check")
    assert r.status_code == 429 and r.json()["error"] == "budget"


def test_guards_without_session_and_unknown_inputs(client: TestClient) -> None:
    assert client.post("/api/check").json()["error"] == "no_session"
    assert client.post("/api/session/start", json={"student_alias": " ", "lab_id": "lab1"}).status_code == 422
    assert client.post("/api/session/start", json={"student_alias": "X", "lab_id": "nope"}).status_code == 404
    assert client.post("/api/demo/scene", json={"step": "s9", "label": "x"}).status_code == 404
    assert client.get("/media/../../etc/passwd").status_code == 404
    assert client.post("/api/debug/thresholds", json={"section": "env", "key": "ta_pin", "value": 1}).status_code == 401
    assert client.post("/api/debug/thresholds", json={"section": "env", "key": "ta_pin", "value": 1},
                       headers=PIN).status_code == 422
    ok = client.post("/api/debug/thresholds", json={"section": "quality", "key": "blur_var_min", "value": 50}, headers=PIN)
    assert ok.status_code == 200 and client.rt.config.settings.quality.blur_var_min == 50.0


def test_ta_skip_and_goto(client: TestClient) -> None:
    client.post("/api/session/start", json={"student_alias": "Jo", "lab_id": "lab1"})
    assert client.post("/api/ta/step/skip").status_code == 401
    state = client.post("/api/ta/step/skip", headers=PIN).json()["state"]
    assert state["current_step_id"] == "s2"
    assert client.post("/api/session/goto", json={"step_id": "s1"}).json()["state"]["current_step_id"] == "s1"
    assert client.post("/api/session/goto", json={"step_id": "s5"}).status_code == 422


def test_stream_and_frames(client: TestClient) -> None:
    r = client.get("/stream.mjpg?frames=1")
    assert r.status_code == 200 and r.content.startswith(b"--frame") and b"\xff\xd8" in r.content
    r2 = client.get("/stream.mjpg?view=warped&frames=1")
    assert b"\xff\xd8" in r2.content
    assert client.get("/api/frame/warped.jpg").headers["content-type"] == "image/jpeg"


def test_power_test_without_light_is_physical_fix(client: TestClient) -> None:
    client.post("/api/session/start", json={"student_alias": "Zed", "lab_id": "lab1"})
    for step in ("s1", "s2", "s3", "s4", "s5"):
        scene(client, step, "correct")
        check(client)
    assert client.get("/api/session/current").json()["baseline_ready"] is True
    scene(client, "s6", "E_NO_LIGHT")
    first = check(client)
    assert first["verdict"]["reason"] == "led:not_lit" and first["help"] is None
    second = check(client)
    assert second["help"]["trigger"] == "power_test"  # two failed power tests → TA notified
