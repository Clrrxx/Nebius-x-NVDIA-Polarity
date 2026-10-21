"""Keep the README's live sections in sync: the model table (after ``verify``) and the eval headline (after a real
``eval``). Only the text between the HTML comment markers is replaced; nothing else in the README changes.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from polarity import paths

USES = {
    "perception": "Step verification (top-down photo ± the student's voice clip), voice Q&A, reading lab-sheet pages, printed part markings",
    "fast_text": "Intent of a typed question; shortening long spoken feedback",
    "reasoning": "TA help-request summaries, assembling compiled labs, the Tavily part-lookup agent",
    "deep": "End-of-class report for the TA",
}


def readme_path() -> Path:
    """README next to the docs folder (tests redirect docs to a temp dir, so they can never edit the real README)."""
    return paths.docs_dir().parent / "README.md"


def _replace_block(text: str, name: str, body: str) -> str:
    pattern = re.compile(rf"(<!-- {name}:START -->\n).*?(\n<!-- {name}:END -->)", re.S)
    if not pattern.search(text):
        return text
    return pattern.sub(lambda m: m.group(1) + body.strip("\n") + m.group(2), text)


def _write(readme: Path, name: str, body: str) -> bool:
    if not readme.exists():
        return False
    text = readme.read_text(encoding="utf-8")
    new = _replace_block(text, name, body)
    if new != text:
        readme.write_text(new, encoding="utf-8")
        return True
    return False


def models_block(caps: dict[str, Any]) -> str:
    rows = ["| Role | Exact model ID on Token Factory | Case used | Measured latency (Phase 0) | Used for |",
            "|---|---|---|---|---|"]
    for role in ("perception", "fast_text", "reasoning", "deep"):
        m = (caps.get("models") or {}).get(role) or {}
        mid = m.get("id")
        lat = m.get("latency_ms")
        rows.append(f"| `{role}` | {('`' + mid + '`') if mid else '—'} | {m.get('case') or '—'} | "
                    f"{(str(lat) + ' ms') if lat is not None else '—'} | {USES[role]} |")
    rows.append("")
    rows.append(f"Verified {caps.get('generated_at', '')} at `{caps.get('base_url')}` · combined image + audio: "
                f"`{caps.get('combined_image_audio')}` · JSON mode: `{caps.get('json_mode')}` · thinking control: "
                f"`{caps.get('thinking_control')}` · tools: `{caps.get('tools_mode')}` · audio mode: "
                f"`{caps.get('audio_mode_recommended')}` (full evidence: [docs/PHASE0_REPORT.md](docs/PHASE0_REPORT.md)).")
    return "\n".join(rows)


def update_readme_models(caps: dict[str, Any], readme: Path | None = None) -> bool:
    return _write(readme or readme_path(), "MODELS", models_block(caps))


def eval_block(summary: Any) -> str:
    def pct(x: float | None) -> str:
        return "n/a" if x is None else f"{100 * x:.1f}%"

    gate = {True: "met", False: "not met", None: "n/a"}[summary.gate_met]
    return "\n".join([
        f"Real photos from our rig, run `{summary.run_id}` ({summary.n} images, models: "
        f"{', '.join(summary.model_ids) or 'n/a'}, prompt hash `{summary.prompt_hash}`):",
        "",
        "| False-pass rate | Selective accuracy | Coverage | Error-ID hit rate | Latency p50 / p95 |",
        "|---|---|---|---|---|",
        f"| **{pct(summary.false_pass_rate)}** | {pct(summary.selective_accuracy)} | {pct(summary.coverage)} | "
        f"{pct(summary.error_id_hit_rate)} | {summary.latency_p50_ms if summary.latency_p50_ms is not None else 'n/a'} / "
        f"{summary.latency_p95_ms if summary.latency_p95_ms is not None else 'n/a'} ms |",
        "",
        f"Decision gate (false-pass ≤ 5%, selective accuracy ≥ 85%): **{gate}**. Full tables, confusion matrix and the "
        "tuning log: [docs/EVAL_RESULTS.md](docs/EVAL_RESULTS.md).",
    ])


def update_readme_eval(summary: Any, readme: Path | None = None) -> bool:
    if getattr(summary, "mock", False):
        return False  # mock numbers never reach the README
    return _write(readme or readme_path(), "EVAL", eval_block(summary))
