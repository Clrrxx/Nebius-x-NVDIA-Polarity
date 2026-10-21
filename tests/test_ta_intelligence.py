"""Phase 4: escalation helpers, background diagnosis, seeded class (flags + shape), class report."""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from polarity.config import get_config
from polarity.demo.seed import FIRST_TRY, seed_class
from polarity.engine import analytics
from polarity.engine.report import SIMULATED_NOTE, ensure_simulated_first_line, render_markdown
from polarity.engine.session_engine import is_safety_redirect
from polarity.models.lab import load_lab
from polarity.storage.db import Database

PIN = {"X-TA-PIN": "2468"}


@pytest.mark.parametrize(("text", "expected"), [
    ("Switch the battery off now and call your TA.", True),
    ("That smells like burning — call the TA right away.", True),
    ("Unplug it and ask your TA to check the battery.", True),
    ("Call the TA if you're stuck on this step.", False),          # no hazard, no switch-off: not a safety redirect
    ("Turn the LED around so the long leg is in strip 10.", False),
    (None, False),
])
def test_safety_redirect_detection(text: str | None, expected: bool) -> None:
    assert is_safety_redirect(text) is expected


def _wait(pred, timeout: float = 5.0) -> bool:  # noqa: ANN001
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.05)
    return False


def test_help_request_gets_background_diagnosis(client: TestClient) -> None:
    client.post("/api/session/start", json={"student_alias": "Ari", "lab_id": "lab1"})
    help_id = client.post("/api/help").json()["help"]["id"]
    rt = client.rt  # type: ignore[attr-defined]
    assert _wait(lambda: rt.db.get_help(help_id).summary_json is not None)
    summary = json.loads(rt.db.get_help(help_id).summary_json)
    assert summary["summary_for_ta"] and summary["urgency"] in ("low", "medium", "high")
    assert summary["model_id"] == "MOCK"
    item = client.get("/api/ta/help", headers=PIN).json()["items"][0]
    assert item["summary"]["summary_for_ta"] == summary["summary_for_ta"]


def test_seed_flags_shape_and_clear(isolated_env) -> None:  # noqa: ANN001
    cfg = get_config()
    db = Database(cfg.paths.db)
    lab = load_lab(cfg.paths.labs / "lab1.yaml")
    real = db.create_session("RealStudent", "lab1")
    counts = seed_class(db, lab, 28)
    assert counts["sessions"] == 28 and 4 <= counts["help"] <= 6
    sims = [s for s in db.list_sessions("lab1") if s.is_simulated]
    assert len(sims) == 28
    assert all(a.is_simulated for s in sims for a in db.list_attempts(s.id))
    assert all(h.is_simulated for h in db.list_help(None))
    ov = analytics.overview(analytics.ClassData(db, lab))
    assert ov["simulated"] is True and ov["completed"] < 28  # some students are still working
    for s in ov["insights"]:
        assert abs(s["first_try_pass_pct"] / 100 - FIRST_TRY[s["step_id"]]) <= 0.12
    top = {s["step_id"]: s["top_errors"][0]["error_id"] for s in ov["insights"] if s["top_errors"]}
    assert top["s3"] == "E_LED_REVERSED"
    checks = [a for s in sims for a in db.list_attempts(s.id) if a.kind == "check"]
    uncertain = sum(a.status == "uncertain" for a in checks) / len(checks)
    assert 0.04 <= uncertain <= 0.12
    assert db.clear_simulated() == 28 and not db.has_simulated()
    assert db.get_session(real.id) is not None


def test_simulated_note_is_enforced() -> None:
    assert ensure_simulated_first_line("## Snapshot\nx", True).startswith(SIMULATED_NOTE)
    assert ensure_simulated_first_line("Simulated data. ## Snapshot", True).startswith("Simulated")
    assert ensure_simulated_first_line("## Snapshot", False) == "## Snapshot"


def test_report_markdown_never_renders_raw_html() -> None:
    out = render_markdown("## Hi\n<img src=x onerror=alert(1)>\n\n| a | b |\n|---|---|\n| 1 | 2 |")
    assert "<img" not in out and "&lt;img" in out and "<table>" in out


def test_report_end_to_end_on_seeded_class(client: TestClient) -> None:
    assert client.post("/api/demo/seed", json={"students": 28}).status_code == 401
    seeded = client.post("/api/demo/seed", json={"students": 28}, headers=PIN).json()
    assert seeded["sessions"] == 28
    overview = client.get("/api/ta/overview", headers=PIN).json()
    assert overview["simulated"] is True and overview["sessions"] == 28
    heat = client.get("/api/ta/heatmap", headers=PIN).json()
    states = {c["state"] for r in heat["rows"] for c in r["cells"]}
    assert {"passed_first", "passed_after"} <= states
    assert client.post("/api/ta/report", json={}).status_code == 401
    report = client.post("/api/ta/report", json={}, headers=PIN).json()
    first_line = next(line for line in report["markdown"].splitlines() if line.strip())
    assert "simulated" in first_line.lower()
    assert report["model_id"] == "MOCK" and "<h2>" in report["html"]
    stats = json.loads(client.rt.db.get_report(report["id"]).input_stats_json)  # type: ignore[attr-defined]
    assert stats["simulated_records"] == 28 and stats["sessions"] == 28
    md = client.get(f"/api/ta/report/{report['id']}.md", headers=PIN)
    assert md.status_code == 200 and md.headers["content-type"].startswith("text/markdown")
    assert client.get(f"/api/ta/report/{report['id']}", headers=PIN).json()["id"] == report["id"]
    timeline_session = heat["rows"][0]["session_id"]
    items = client.get(f"/api/ta/session/{timeline_session}/timeline", headers=PIN).json()["items"]
    assert items and all(i["is_simulated"] for i in items)
    assert client.request("DELETE", "/api/demo/seed", headers=PIN).json()["removed_sessions"] == 28
    assert client.get("/api/ta/overview", headers=PIN).json()["simulated"] is False


def test_report_without_simulated_data_has_no_note(client: TestClient) -> None:
    client.post("/api/session/start", json={"student_alias": "Solo", "lab_id": "lab1"})
    report = client.post("/api/ta/report", json={"lab_id": "lab1"}, headers=PIN).json()
    assert SIMULATED_NOTE not in report["markdown"]
