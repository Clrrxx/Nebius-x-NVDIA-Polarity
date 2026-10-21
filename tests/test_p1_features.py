"""Phase 5 (P1): lab compiler, Tavily part lookup, board audit, hub mode."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from polarity import config as config_mod
from polarity.engine import lab_compiler as lc
from polarity.engine import parts as parts_mod
from tests import fake_token_factory as fake

PIN = {"X-TA-PIN": "2468"}
ROOT = Path(__file__).resolve().parents[1]


def _wait(pred, timeout: float = 10.0) -> bool:  # noqa: ANN001
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.05)
    return False


# ── lab compiler ──────────────────────────────────────────────────────────────────────────────

def test_render_pages_from_sample_pdf_and_images(tmp_path: Path) -> None:
    pdf = (ROOT / "labs" / "samples" / "lab1_handout.pdf").read_bytes()
    pages = lc.render_pages("handout.pdf", pdf, tmp_path / "a")
    assert 2 <= len(pages) <= lc.MAX_PAGES and all(p.suffix == ".png" for p in pages)
    png = pages[0].read_bytes()
    assert len(lc.render_pages("photo.png", png, tmp_path / "b")) == 1
    with pytest.raises(lc.CompileError):
        lc.render_pages("notes.txt", b"hello", tmp_path / "c")


def test_compile_flow_draft_then_publish(client: TestClient) -> None:
    assert client.post("/api/labs/compile", data={"sample": "true"}).status_code == 401
    est = client.post("/api/labs/compile", data={"sample": "true"}, headers=PIN).json()
    assert est["estimate"]["pages"] == len(est["pages"]) and est["estimate"]["cost_estimate_usd"] is None
    assert client.get(est["pages"][0]).headers["content-type"] == "image/png"
    started = client.post("/api/labs/compile", data={"upload_id": est["upload_id"], "confirm": "true"}, headers=PIN).json()
    assert started["started"] is True
    rt = client.rt  # type: ignore[attr-defined]
    assert _wait(lambda: rt.labs.get("lab_compiled_mock") is not None)
    draft = client.get("/api/labs/lab_compiled_mock").json()
    assert draft["source"] == "draft" and draft["lab"]["ai_drafted"] is True
    assert any(i["id"] == "lab_compiled_mock" and i["source"] == "draft" for i in client.get("/api/labs").json()["items"])
    bad = dict(draft["lab"], steps=[])
    resp = client.put("/api/labs/lab_compiled_mock", json={"lab": bad, "publish": True}, headers=PIN)
    assert resp.status_code == 422 and "step" in resp.json()["message"]
    ok = client.put("/api/labs/lab_compiled_mock", json={"lab": draft["lab"], "publish": True}, headers=PIN).json()
    assert ok["published"] is True
    published = config_mod.get_config().paths.labs / "lab_compiled_mock.yaml"
    assert published.exists() and "ai_drafted: false" in published.read_text(encoding="utf-8")
    assert not (config_mod.get_config().paths.drafts / "lab_compiled_mock.yaml").exists()
    assert not (ROOT / "labs" / "lab_compiled_mock.yaml").exists()  # tests never write into the repo


def test_editor_page_needs_pin(client: TestClient) -> None:
    assert "TA PIN" in client.get("/labs/editor").text
    assert 'id="labform"' in client.get("/labs/editor", headers=PIN).text


# ── Tavily part lookup ────────────────────────────────────────────────────────────────────────

class FakeTavily:
    calls: list[str] = []

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def search(self, query: str, **kw) -> dict:  # noqa: ANN003
        FakeTavily.calls.append(query)
        assert kw == {"max_results": 5, "search_depth": "basic", "include_answer": False}
        return {"results": [{"title": "NE555 datasheet", "url": "https://www.ti.com/lit/ds/symlink/ne555.pdf",
                             "content": "Pin 1 GND, pin 8 VCC"},
                            {"title": "555 timer pinout", "url": "https://example.edu/555", "content": "pins"},
                            {"title": "bad", "url": "javascript:alert(1)", "content": "x"}]}


def test_part_lookup_requires_key(client: TestClient) -> None:
    r = client.post("/api/parts/lookup", json={"part": "NE555"})
    assert r.status_code == 503 and r.json()["error"] == "parts_unavailable"


def test_part_lookup_manual_mode_uses_real_sources(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    FakeTavily.calls = []
    monkeypatch.setattr(parts_mod, "make_tavily_client", FakeTavily)
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key-0000")
    client.rt.config.env.tavily_api_key = config_mod.SecretStr("tvly-test-key-0000")  # type: ignore[attr-defined]
    r = client.post("/api/parts/lookup", json={"part": "ne555"}).json()
    assert FakeTavily.calls == ["NE555 pinout datasheet"]
    assert r["sources"] == ["https://www.ti.com/lit/ds/symlink/ne555.pdf", "https://example.edu/555"]
    assert r["result_count"] == 2 and r["model_id"] == "MOCK"
    again = client.post("/api/parts/lookup", json={"part": "NE555"}).json()
    assert again["cached"] is True and len(FakeTavily.calls) == 1
    assert client.post("/api/parts/lookup", json={"part": "<script>"}).status_code == 422


def test_part_lookup_native_tool_call(fake_token_factory: str, monkeypatch: pytest.MonkeyPatch, isolated_env: Path) -> None:
    from polarity.runtime import Runtime

    FakeTavily.calls = []
    monkeypatch.setattr(parts_mod, "make_tavily_client", FakeTavily)
    monkeypatch.setenv("POLARITY_MOCK_MODELS", "0")
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key-0000-9999")
    monkeypatch.setenv("NEBIUS_BASE_URL", fake_token_factory)
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test-key-0000")
    caps = {"base_url": fake_token_factory, "json_mode": "json_object", "tools_mode": "native",
            "thinking_control": "chat_template_kwargs", "models": {"reasoning": {"id": fake.SUPER, "case": "exact"}}}
    (isolated_env / "data" / "capabilities.json").write_text(json.dumps(caps), encoding="utf-8")
    config_mod.reset_config()
    rt = Runtime(config_mod.get_config())
    result = parts_mod.lookup(rt, "NE555")
    assert FakeTavily.calls == ["NE555 pinout datasheet"]          # the model asked for the tool, our code ran Tavily
    assert result["mode"] == "native" and result["model_id"] == fake.SUPER
    assert "https://invented.example/fake" not in result["sources"]  # never cite a URL Tavily did not return
    assert result["pinout"][0] == {"pin": "1", "name": "GND"}


# ── board audit ───────────────────────────────────────────────────────────────────────────────

def test_board_audit_ranks_suspects(client: TestClient) -> None:
    assert client.post("/api/audit").status_code == 409
    client.post("/api/session/start", json={"student_alias": "Ada", "lab_id": "lab1"})
    client.post("/api/demo/scene", json={"step": "s3", "label": "E_LED_REVERSED"})
    r = client.post("/api/audit").json()
    assert r["suspects"][0]["step_id"] == "s3" and r["suspects"][0]["check_id"] == "c_orientation"
    assert r["spoken_feedback"] and r["model_id"] == "MOCK"
    rt = client.rt  # type: ignore[attr-defined]
    assert [a.kind for a in rt.db.list_attempts(rt.engine.session.id)] == ["audit"]
    client.post("/api/demo/scene", json={"step": "s3", "label": "_dark"})
    assert client.post("/api/audit").status_code == 422  # unusable image → no cloud call


# ── hub mode ──────────────────────────────────────────────────────────────────────────────────

def test_hub_sync_with_outbox_and_retry(isolated_env: Path, demo_set: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from polarity.hub.client import HubClient
    from polarity.runtime import Runtime
    from polarity.web.app import create_app

    hub_dir, bench_dir = isolated_env / "hub", isolated_env / "bench"
    shutil.copytree(demo_set, bench_dir / "demo" / "lab1")
    monkeypatch.setenv("POLARITY_DATA_DIR", str(hub_dir))
    hub_cfg = config_mod.load_config()
    hub_cfg.role_override = "hub"
    monkeypatch.setenv("POLARITY_DATA_DIR", str(bench_dir))
    bench_cfg = config_mod.load_config()
    bench_cfg.role_override, bench_cfg.hub_url, bench_cfg.bench_id = "bench", "http://hub.local:8765", "B07"
    hub_rt, bench_rt = Runtime(hub_cfg), Runtime(bench_cfg)
    assert hub_rt.camera.status()["source"] == "none"

    reachable = {"up": False}
    holder: dict[str, TestClient] = {}

    def post(url: str, body: dict, headers: dict) -> int:
        if not reachable["up"]:
            raise ConnectionError("hub offline")
        return holder["hub"].post("/api/hub/ingest", json=body, headers=headers).status_code

    # Installed before startup, so no real network sync thread is ever created in tests.
    bench_rt.hub_client = HubClient(bench_rt, bench_cfg.hub_url, post=post)
    with TestClient(create_app(hub_rt)) as hub, TestClient(create_app(bench_rt)) as bench:
        holder["hub"] = hub
        bench.post("/api/session/start", json={"student_alias": "Remy", "lab_id": "lab1", "bench_id": "B07"})
        bench.post("/api/demo/scene", json={"step": "s1", "label": "correct"})
        bench.post("/api/check")
        bench.post("/api/help")
        assert bench_rt.hub_client.flush() == 0 and bench_rt.hub_client.pending() >= 3   # queued while offline
        reachable["up"] = True
        assert bench_rt.hub_client.flush() >= 3 and bench_rt.hub_client.pending() == 0
        sessions = hub_rt.db.list_sessions()
        assert [s.student_alias for s in sessions] == ["Remy"] and sessions[0].bench_id == "B07"
        attempts = hub_rt.db.list_attempts(sessions[0].id)
        assert attempts and attempts[0].warped_image_path is None  # thumbnails are off by default (privacy)
        assert hub_rt.db.list_help("open")
        heat = hub.get("/api/ta/heatmap", headers=PIN).json()
        assert heat["rows"][0]["alias"] == "Remy" and heat["rows"][0]["cells"][0]["state"] == "passed_first"
        assert hub.post("/api/hub/ingest", json={"kind": "session", "payload": {}}).status_code == 401
        assert bench.post("/api/hub/ingest", json={"kind": "session", "payload": {}}, headers=PIN).status_code == 409
