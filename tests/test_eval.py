"""Eval harness: mock run end to end on a synthetic subset; real runs refuse to fake results without a key."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from polarity.cli import app
from polarity.config import get_config
from polarity.demo.synthetic_board import render_all
from polarity.engine.evaluate import discover, render_report, run_eval, summarise, write_outputs
from polarity.models.lab import load_lab


def test_mock_eval_end_to_end(tmp_path: Path) -> None:
    cfg = get_config()
    lab = load_lab(cfg.paths.labs / "lab1.yaml")
    dataset = tmp_path / "demo"
    render_all(dataset, steps=["s3", "s5", "s6"])
    samples = discover(dataset, lab)
    assert {s.label for s in samples} >= {"correct", "E_LED_REVERSED", "E_NO_LIGHT"}
    assert not any(s.label.startswith("_") for s in samples)
    summary, preds = run_eval(cfg, dataset, lab, mock=True)
    assert summary.mock and summary.n == len(samples)
    assert summary.false_pass_rate == 0.0 and summary.coverage == 1.0
    out = write_outputs(summary, preds, cfg)
    report = out["report"].read_text(encoding="utf-8")
    assert "MOCK RUN: NOT EVIDENCE" in report and "False-pass rate" in report
    assert not (cfg.paths.docs / "EVAL_RESULTS.md").exists()  # mock runs never write docs/
    assert out["csv"].read_text(encoding="utf-8").startswith("step_id,label,file")


def test_team_photos_override_synthetic(tmp_path: Path) -> None:
    lab = load_lab(get_config().paths.labs / "lab1.yaml")
    dataset = tmp_path / "demo"
    render_all(dataset, steps=["s3"], labels=["correct"])
    real = dataset / "s3" / "correct.jpg"
    real.write_bytes((dataset / "s3" / "correct.png").read_bytes())
    samples = discover(dataset, lab)
    assert [(s.path.name, s.synthetic) for s in samples] == [("correct.jpg", False)]


def test_capture_folder_layout_is_discovered(tmp_path: Path) -> None:
    lab = load_lab(get_config().paths.labs / "lab1.yaml")
    folder = tmp_path / "eval" / "s3" / "E_LED_REVERSED"
    folder.mkdir(parents=True)
    for name in ("0001_raw.jpg", "0001_warped.jpg", "0002_raw.jpg"):
        (folder / name).write_bytes(b"x")
    samples = discover(tmp_path / "eval", lab)
    assert [s.path.name for s in samples] == ["0001_raw.jpg", "0002_raw.jpg"]
    assert all(s.expected == "fix" and s.error_id == "E_LED_REVERSED" for s in samples)


def test_real_report_preserves_change_log(tmp_path: Path) -> None:
    from polarity.engine.evaluate import Prediction

    cfg = get_config()
    preds = [Prediction("s3", "correct", "a.jpg", "pass", "pass", "model:pass", 0.9, [], None, False, "m", 1200, None, True),
             Prediction("s3", "E_LED_REVERSED", "b.jpg", "fix", "pass", "model:pass", 0.9, [], None, False, "m", 1500,
                        None, True)]
    summary = summarise(preds, "20261026-101500", False, "data/eval/lab1")
    assert summary.false_pass_rate == 1.0 and summary.gate_met is False
    existing = "# x\n\n## What we changed after eval\nIteration 1: moved the lamp.\n\n## Run history\n| 20261025-0900 | a |\n"
    text = render_report(summary, preds, cfg, existing)
    assert "Iteration 1: moved the lamp." in text and "| 20261025-0900 | a |" in text and "| 20261026-101500" in text


def test_real_eval_without_key_is_pending(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("POLARITY_MOCK_MODELS", "0")
    from polarity import config

    config.reset_config()
    result = CliRunner().invoke(app, ["eval"])
    assert result.exit_code == 2 and "PENDING" in result.output
