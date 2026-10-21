"""Storage (SQLite + media sandbox), lab/verdict/capability schemas, and config loading on awkward paths."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path, PureWindowsPath

import numpy as np
import pytest
from pydantic import ValidationError

from polarity import config as config_mod
from polarity.models.capabilities import Capabilities
from polarity.models.lab import LabDefinition, list_labs, load_lab
from polarity.models.session import Attempt
from polarity.models.verdict import FinalVerdict
from polarity.storage.db import Database, now_iso
from polarity.storage.media import MediaStore

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("name", ["lab1", "lab1_5v", "lab2_solder_template"])
def test_shipped_labs_validate(name: str) -> None:
    lab = load_lab(ROOT / "labs" / f"{name}.yaml")
    assert lab.id == name and lab.steps
    for step in lab.steps:
        for err in step.common_errors:
            assert err.fix_hint_l1 and err.fix_hint_l2 and err.fix_hint_l3 and err.visual_cue


def test_lab1_matches_spec() -> None:
    lab = load_lab(ROOT / "labs" / "lab1.yaml")
    assert [s.id for s in lab.steps] == ["s1", "s2", "s3", "s4", "s5", "s6"]
    assert lab.step("s3").check("c_orientation").allow_uncertain  # type: ignore[union-attr]
    assert lab.step("s4").check("c_btn_rotation").allow_uncertain  # type: ignore[union-attr]
    assert lab.step("s6").led_check and lab.step("s6").led_check.expect_lit  # type: ignore[union-attr]
    assert lab.step("s3").error("E_LED_REVERSED").fix_hint_l1.startswith("Take a close look")  # type: ignore[union-attr]
    assert set(list_labs(ROOT / "labs")) >= {"lab1", "lab1_5v", "lab2_solder_template"}


def test_lab_validation_rejects_bad_definitions() -> None:
    data = load_lab(ROOT / "labs" / "lab1.yaml").model_dump()
    data["steps"][0]["common_errors"][0]["related_checks"] = ["c_does_not_exist"]
    with pytest.raises(ValidationError):
        LabDefinition.model_validate(data)
    data = load_lab(ROOT / "labs" / "lab1.yaml").model_dump()
    data["steps"][1]["id"] = "s1"
    with pytest.raises(ValidationError):
        LabDefinition.model_validate(data)


def test_capabilities_defaults_and_loading(tmp_path: Path) -> None:
    caps = Capabilities.load(tmp_path / "missing.json")
    assert not caps.verified and caps.json_mode == "prompt_only" and caps.audio_mode_recommended == "browser_stt"
    example = Capabilities.load(ROOT / "data" / "capabilities.example.json")
    assert example.verified is False and example.models["perception"].id
    (tmp_path / "caps.json").write_text("{not json", encoding="utf-8")
    assert Capabilities.load(tmp_path / "caps.json").verified is False


def test_final_verdict_roundtrip() -> None:
    fv = FinalVerdict(status="uncertain", reason="quality:glare", retake_instruction="tilt")
    assert FinalVerdict.model_validate_json(fv.model_dump_json()) == fv


def test_database_crud_and_spend(tmp_path: Path) -> None:
    db = Database(tmp_path / "p.db")
    s = db.create_session("Robin", "lab1", "B07")
    db.add_attempt(Attempt(id="a1", session_id=s.id, step_id="s1", kind="check", status="fix", created_at=now_iso()))
    db.add_attempt(Attempt(id="a2", session_id=s.id, step_id="s1", kind="check", status="pass", created_at=now_iso()))
    assert [a.id for a in db.list_attempts(s.id, "s1")] == ["a1", "a2"]
    h = db.add_help(s.id, "s1", "call_ta")
    db.update_help_summary(h.id, {"summary_for_ta": "x"})
    assert db.list_help("open")[0].summary_json
    assert db.resolve_help(h.id) and not db.resolve_help(h.id)
    db.record_model_call(role="perception", model_id="m", ok=True, latency_ms=10, prompt_tokens=5,
                         completion_tokens=5, cost_usd=0.25, error=None, session_id=s.id)
    db.record_model_call(role="deep", model_id="m", ok=True, latency_ms=10, prompt_tokens=5, completion_tokens=5,
                         cost_usd=None, error=None, session_id=None)
    assert db.spend(s.id) == (0.25, 0.25)
    assert len(db.recent_model_calls()) == 2
    db.put_part("ne555", {"summary": "timer"})
    assert db.get_part("NE555") == {"summary": "timer"}


def test_simulated_rows_are_flagged_and_clearable(tmp_path: Path) -> None:
    db = Database(tmp_path / "p.db")
    real = db.create_session("Real", "lab1")
    sim = db.create_session("Sim", "lab1", is_simulated=True)
    db.add_attempt(Attempt(id="x", session_id=sim.id, step_id="s1", created_at=now_iso(), is_simulated=True))
    assert db.has_simulated()
    assert db.clear_simulated() == 1
    assert not db.has_simulated() and db.get_session(real.id) and not db.list_attempts(sim.id)


def test_media_store_sandbox_and_purge(tmp_path: Path) -> None:
    store = MediaStore(tmp_path / "media")
    rel = store.save_image("sess", "a_warped.jpg", np.zeros((10, 10, 3), np.uint8))
    assert rel == "sess/a_warped.jpg" and store.resolve(rel) is not None
    assert store.resolve("../../etc/passwd") is None
    assert store.resolve("sess/../../outside.txt") is None
    old = time.time() - 30 * 86400
    for f in (tmp_path / "media" / "sess").iterdir():
        os.utime(f, (old, old))
    assert store.purge(14) == 1 and not (tmp_path / "media" / "sess").exists()


def test_config_loads_from_paths_with_spaces_and_unicode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    odd = tmp_path / "Hasif's Lab Folder" / "dätä dir"
    odd.mkdir(parents=True)
    env = tmp_path / "with space.env"
    env.write_text("TA_PIN=9999\nCAMERA_INDEX=2\nNEBIUS_BASE_URL=\nAUDIO_MODE=typed   # comment\n", encoding="utf-8")
    monkeypatch.setenv("POLARITY_DATA_DIR", str(odd))
    monkeypatch.setenv("POLARITY_ENV_FILE", str(env))
    monkeypatch.delenv("CAMERA_SOURCE", raising=False)
    (odd / "capabilities.json").write_text(json.dumps({"json_mode": "json_object"}), encoding="utf-8")
    config_mod.reset_config()
    cfg = config_mod.get_config()
    assert cfg.paths.data == odd.resolve() and cfg.paths.db.parent == odd.resolve()
    assert cfg.env.ta_pin.get_secret_value() == "9999" and cfg.env.camera_index == 2
    assert cfg.env.nebius_base_url is None  # empty values are ignored
    assert cfg.audio_mode() == "typed"
    assert cfg.capabilities.json_mode == "json_object" and cfg.capabilities.verified


def test_windows_style_relative_paths_normalise() -> None:
    rel = PureWindowsPath(r"data\demo\lab1\s3\correct.png")
    assert Path(*rel.parts).as_posix() == "data/demo/lab1/s3/correct.png"
