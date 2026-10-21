"""Evaluation harness (BUILD_PROMPT.md 14.3): ``python -m polarity eval --dataset data/eval/lab1 [--limit N]``.

Runs the real check pipeline (warp → quality gate → perception → decision → second look) over labelled photos.
Ground truth: ``correct`` → pass (pass_partial counts as pass); ``E_*`` → fix, ideally naming that error id.
Labels starting with ``_`` are special scenes and are skipped (``_baseline`` holds LED-off photos for the
power-test step).

Real runs write ``docs/EVAL_RESULTS.md`` and ``docs/eval_predictions.csv``, the only numbers the README, Devpost
text or video may quote. ``--mock`` runs (synthetic images + canned answers) write ONLY under
``data/eval_runs/`` and are labelled as not evidence.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from polarity.cvio import imread
from polarity.demo.synthetic_board import SYNTHETIC_MANIFEST
from polarity.llm.prompts import prompt_hash
from polarity.models.lab import LabDefinition

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
TARGET_FALSE_PASS = 0.05
TARGET_SELECTIVE_ACC = 0.85
CHANGES_HEADING = "## What we changed after eval"
HISTORY_HEADING = "## Run history"


@dataclass
class Sample:
    step_id: str
    label: str
    path: Path
    expected: str            # "pass" | "fix"
    error_id: str | None
    synthetic: bool = False


@dataclass
class Prediction:
    step_id: str
    label: str
    file: str
    expected: str
    predicted: str
    reason: str
    confidence: float | None
    detected_error_ids: list[str]
    error_id_hit: bool | None
    second_look: bool
    model_id: str | None
    latency_ms: int | None
    cost_usd: float | None
    model_called: bool


@dataclass
class EvalSummary:
    run_id: str
    mock: bool
    dataset: str
    n: int
    coverage: float | None
    selective_accuracy: float | None
    false_pass_rate: float | None
    error_id_hit_rate: float | None
    uncertain_rate_by_step: dict[str, float]
    latency_p50_ms: float | None
    latency_p95_ms: float | None
    cost_per_check_usd: float | None
    confusion: dict[str, dict[str, int]]
    gate_met: bool | None
    model_ids: list[str] = field(default_factory=list)
    prompt_hash: str = ""


def _synthetic_files(dataset: Path) -> set[str]:
    manifest = dataset / SYNTHETIC_MANIFEST
    if not manifest.exists():
        return set()
    return set(json.loads(manifest.read_text(encoding="utf-8")).get("files", []))


def _label_info(label: str) -> tuple[str, str | None] | None:
    if label == "correct":
        return "pass", None
    if label.startswith("E_"):
        return "fix", label
    return None


def discover(dataset: Path, lab: LabDefinition) -> list[Sample]:
    """Find labelled images. Supports ``<step>/<label>/*.jpg`` (capture tool) and ``<step>/<label>.png`` (demo set).
    When both a synthetic render and a team photo exist for one label, the team photo wins."""
    synthetic = _synthetic_files(dataset)
    samples: list[Sample] = []
    for step in lab.steps:
        step_dir = dataset / step.id
        if not step_dir.is_dir():
            continue
        by_label: dict[str, list[Path]] = {}
        for entry in sorted(step_dir.iterdir()):
            if entry.is_dir():
                files = sorted(p for p in entry.iterdir() if p.suffix.lower() in IMAGE_EXT)
                raws = [p for p in files if "_raw" in p.stem]
                by_label.setdefault(entry.name, []).extend(raws or [p for p in files if "_warped" not in p.stem])
            elif entry.suffix.lower() in IMAGE_EXT:
                by_label.setdefault(entry.stem, []).append(entry)
        for label, files in by_label.items():
            info = _label_info(label)
            if info is None:
                continue
            rel = {f: f.relative_to(dataset).as_posix() for f in files}
            real = [f for f in files if rel[f] not in synthetic]
            for f in (real or files):
                samples.append(Sample(step.id, label, f, info[0], info[1], synthetic=rel[f] in synthetic))
    return samples


def _baseline_for(dataset: Path, lab: LabDefinition, step_id: str, synthetic: bool) -> Path | None:
    folder = dataset / step_id / "_baseline"
    if folder.is_dir():
        files = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXT)
        if files:
            return files[0]
    if synthetic:  # demo set: the board as built at the end of the previous step (LED off)
        idx = lab.step_index(step_id)
        if idx > 0:
            prev = dataset / lab.steps[idx - 1].id / "correct.png"
            if prev.exists():
                return prev
    return None


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{100 * x:.1f}%"


def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    values = sorted(values)
    k = (len(values) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (k - lo)


def summarise(preds: list[Prediction], run_id: str, mock: bool, dataset: str) -> EvalSummary:
    n = len(preds)
    decided = [p for p in preds if p.predicted != "uncertain"]

    def correct(p: Prediction) -> bool:
        return (p.expected == "pass" and p.predicted in ("pass", "pass_partial")) or \
               (p.expected == "fix" and p.predicted == "fix")

    wrong_builds = [p for p in preds if p.expected == "fix"]
    fixes = [p for p in wrong_builds if p.predicted == "fix"]
    by_step: dict[str, list[Prediction]] = {}
    for p in preds:
        by_step.setdefault(p.step_id, []).append(p)
    latencies = [float(p.latency_ms) for p in preds if p.model_called and p.latency_ms is not None]
    costs = [p.cost_usd for p in preds if p.model_called]
    confusion: dict[str, dict[str, int]] = {e: {k: 0 for k in ("pass", "pass_partial", "fix", "uncertain")}
                                            for e in ("pass", "fix")}
    for p in preds:
        confusion[p.expected][p.predicted] += 1
    sel = (sum(correct(p) for p in decided) / len(decided)) if decided else None
    fpr = (sum(p.predicted in ("pass", "pass_partial") for p in wrong_builds) / len(wrong_builds)) if wrong_builds else None
    return EvalSummary(
        run_id=run_id, mock=mock, dataset=dataset, n=n,
        coverage=(len(decided) / n) if n else None,
        selective_accuracy=sel,
        false_pass_rate=fpr,
        error_id_hit_rate=(sum(bool(p.error_id_hit) for p in fixes) / len(fixes)) if fixes else None,
        uncertain_rate_by_step={s: sum(p.predicted == "uncertain" for p in ps) / len(ps) for s, ps in sorted(by_step.items())},
        latency_p50_ms=_percentile(latencies, 0.5), latency_p95_ms=_percentile(latencies, 0.95),
        cost_per_check_usd=(sum(costs) / len(costs)) if costs and all(c is not None for c in costs) else None,  # type: ignore[arg-type]
        confusion=confusion,
        gate_met=(fpr <= TARGET_FALSE_PASS and sel >= TARGET_SELECTIVE_ACC) if (fpr is not None and sel is not None) else None,
        model_ids=sorted({p.model_id for p in preds if p.model_id}),
        prompt_hash=prompt_hash(),
    )


def run_eval(config: Any, dataset: Path, lab: LabDefinition, limit: int | None = None, mock: bool = False,
             progress: Any = None) -> tuple[EvalSummary, list[Prediction]]:
    """Evaluate every sample (or the first ``limit``). Uses the same Verifier as the bench."""
    from polarity.engine.verifier import CheckRequest, Verifier
    from polarity.llm.router import ModelRouter, RouterError

    samples = discover(dataset, lab)
    if limit:
        samples = samples[:limit]
    router = ModelRouter(config)
    verifier = Verifier(config, router)
    baselines: dict[str, Any] = {}
    preds: list[Prediction] = []
    for i, s in enumerate(samples):
        step = lab.step(s.step_id)
        assert step is not None
        frame = imread(s.path)
        if frame is None:
            continue
        baseline = None
        if step.led_check is not None:
            if s.step_id not in baselines:
                bpath = _baseline_for(dataset, lab, s.step_id, s.synthetic)
                bframe = imread(bpath) if bpath else None
                baselines[s.step_id] = verifier.analyse(bframe)[1] if bframe is not None else None
            baseline = baselines[s.step_id]
        req = CheckRequest(lab=lab, step=step, frame=frame, hint_level=1, motion=0.0, led_baseline=baseline,
                           mock_hint=s.label if mock else None)
        try:
            outcome = verifier.check(req)
            final = outcome.final
            called = bool(outcome.calls)
        except RouterError as exc:
            preds.append(Prediction(s.step_id, s.label, s.path.relative_to(dataset).as_posix(), s.expected, "uncertain",
                                    f"error:{type(exc).__name__}", None, [], None, False, None, None, None, False))
            continue
        detected = final.perception.detected_error_ids if final.perception else []
        hit = (s.error_id in detected) if (s.error_id and final.status == "fix") else None
        preds.append(Prediction(s.step_id, s.label, s.path.relative_to(dataset).as_posix(), s.expected, final.status,
                                final.reason, final.perception.confidence if final.perception else None, detected, hit,
                                final.second_look_used, final.model_id, final.latency_ms, final.cost_usd, called))
        if progress:
            progress(i + 1, len(samples), preds[-1])
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S") + ("_mock" if mock else "")
    try:  # never write absolute local paths (home folder names) into shareable reports
        shown = dataset.resolve().relative_to(config.paths.root.resolve()).as_posix()
    except ValueError:
        shown = dataset.name
    return summarise(preds, run_id, mock, shown), preds


def _settings_snapshot(config: Any) -> dict[str, Any]:
    s = config.settings
    return {"quality": s.quality.model_dump(), "decision": s.decision.model_dump(), "led": s.led.model_dump(),
            "audio_mode": config.audio_mode(), "json_mode": config.capabilities.json_mode,
            "thinking_control": config.capabilities.thinking_control}


def _preserved_sections(existing: str | None) -> tuple[str, list[str]]:
    changes = "_Record each tuning iteration here: what changed (capture/lighting, crop/zoom, prompt wording, " \
              "thresholds, allow_uncertain) and what the next run showed._"
    history: list[str] = []
    if existing:
        m = re.search(re.escape(CHANGES_HEADING) + r"\n(.*?)(?=\n## |\Z)", existing, re.S)
        if m and m.group(1).strip():
            changes = m.group(1).strip()
        h = re.search(re.escape(HISTORY_HEADING) + r"\n(.*?)(?=\n## |\Z)", existing, re.S)
        if h:
            history = [ln for ln in h.group(1).strip().splitlines() if ln.startswith("| 20")]
    return changes, history


def render_report(summary: EvalSummary, preds: list[Prediction], config: Any, existing: str | None = None) -> str:
    """Markdown report for docs/EVAL_RESULTS.md (or the mock copy)."""
    changes, history = _preserved_sections(existing)
    row = (f"| {summary.run_id[:8]}-{summary.run_id[9:15]} | `{summary.prompt_hash}` | {summary.n} | "
           f"{_pct(summary.coverage)} | {_pct(summary.selective_accuracy)} | {_pct(summary.false_pass_rate)} | "
           f"{_pct(summary.error_id_hit_rate)} |")
    if not summary.mock:
        history.append(row)
    lines = []
    if summary.mock:
        lines += ["# Evaluation results (MOCK RUN: NOT EVIDENCE)", "",
                  "> **MOCK MODE: not real AI output.** Synthetic placeholder images and canned model answers. These "
                  "numbers only prove the harness runs end to end. Never quote them as accuracy.", ""]
    else:
        lines += ["# Evaluation results", ""]
    gate = {True: "**MET**", False: "**NOT MET**", None: "n/a"}[summary.gate_met]
    lines += [
        f"- **Run:** `{summary.run_id}` on {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M %z')}",
        f"- **Dataset:** `{summary.dataset}` ({summary.n} images)",
        f"- **Models:** {', '.join(f'`{m}`' for m in summary.model_ids) or 'n/a'}",
        f"- **Prompt hash:** `{summary.prompt_hash}`",
        f"- **Decision gate** (false-pass ≤ {TARGET_FALSE_PASS:.0%} and selective accuracy ≥ "
        f"{TARGET_SELECTIVE_ACC:.0%}): {gate}",
        "",
        "## Headline metrics",
        "",
        "| Metric | Value | Meaning |",
        "|---|---|---|",
        f"| Coverage | {_pct(summary.coverage)} | share of checks that were not CAN'T TELL |",
        f"| Selective accuracy | {_pct(summary.selective_accuracy)} | accuracy among checks that gave a verdict |",
        f"| **False-pass rate** | **{_pct(summary.false_pass_rate)}** | wrong builds marked pass (the most important number) |",
        f"| Error-ID hit rate | {_pct(summary.error_id_hit_rate)} | FIX verdicts that named the right mistake |",
        f"| Latency p50 / p95 | {summary.latency_p50_ms if summary.latency_p50_ms is not None else 'n/a'} / "
        f"{summary.latency_p95_ms if summary.latency_p95_ms is not None else 'n/a'} ms | checks that reached the model |",
        f"| Cost per check | {f'${summary.cost_per_check_usd:.5f}' if summary.cost_per_check_usd is not None else 'n/a'} "
        "| estimated from config/pricing.yaml |",
        "",
        "## Uncertain rate per step",
        "",
        "| Step | CAN'T TELL rate |",
        "|---|---|",
        *[f"| {s} | {_pct(r)} |" for s, r in summary.uncertain_rate_by_step.items()],
        "",
        "## Confusion matrix (rows = ground truth, columns = verdict)",
        "",
        "| Expected \\ Predicted | pass | pass_partial | fix | uncertain |",
        "|---|---|---|---|---|",
        *[f"| {e} | " + " | ".join(str(summary.confusion[e][k]) for k in ("pass", "pass_partial", "fix", "uncertain")) + " |"
          for e in ("pass", "fix")],
        "",
        "## Settings snapshot",
        "",
        "```json",
        json.dumps(_settings_snapshot(config), indent=2),
        "```",
        "",
        CHANGES_HEADING,
        changes,
        "",
        HISTORY_HEADING,
        "| Run | Prompt hash | N | Coverage | Selective acc. | False-pass | Error-ID hit |",
        "|---|---|---|---|---|---|---|",
        *history,
        "",
    ]
    return "\n".join(lines)


def write_outputs(summary: EvalSummary, preds: list[Prediction], config: Any) -> dict[str, Path]:
    """Write the CSV + report. Mock runs never touch docs/."""
    run_dir = config.paths.data / "eval_runs" / summary.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    csv_path = run_dir / "predictions.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(asdict(preds[0]).keys()) if preds else ["file"])
        writer.writeheader()
        for p in preds:
            row = asdict(p)
            row["detected_error_ids"] = ";".join(p.detected_error_ids)
            writer.writerow(row)
    (run_dir / "summary.json").write_text(json.dumps(asdict(summary), indent=2), encoding="utf-8")
    out = {"csv": csv_path, "summary": run_dir / "summary.json"}
    if summary.mock:
        report = run_dir / "EVAL_RESULTS_MOCK.md"
        report.write_text(render_report(summary, preds, config), encoding="utf-8")
        out["report"] = report
        return out
    docs = config.paths.docs
    report = docs / "EVAL_RESULTS.md"
    existing = report.read_text(encoding="utf-8") if report.exists() else None
    report.write_text(render_report(summary, preds, config, existing), encoding="utf-8")
    docs_csv = docs / "eval_predictions.csv"
    docs_csv.write_bytes(csv_path.read_bytes())
    out.update({"report": report, "docs_csv": docs_csv})
    try:
        from polarity.docs_sync import update_readme_eval

        update_readme_eval(summary)
    except Exception:  # noqa: BLE001 - README sync is best-effort
        pass
    return out
