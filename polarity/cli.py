"""Command-line interface (Typer). Every command also works as ``python -m polarity <command>``."""

from __future__ import annotations

import os
from pathlib import Path

import typer

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Polarity: an AI lab partner for breadboard labs (Nebius Token Factory + NVIDIA Nemotron).",
)


@app.callback()
def _root() -> None:
    """Polarity command line. Run a command with --help for its options."""


def _console():  # noqa: ANN202 - rich import kept lazy for fast --help
    from rich.console import Console

    return Console()


@app.command()
def verify(
    record: bool = typer.Option(False, "--record", help="Record the audio test phrase from your microphone."),
    skip_video: bool = typer.Option(False, "--skip-video", help="Skip the optional video test (T9)."),
    as_json: bool = typer.Option(False, "--json", help="Also print capabilities.json to stdout."),
) -> None:
    """Phase 0: verify Token Factory, discover Nemotron model IDs, write data/capabilities.json."""
    from polarity.verify.run_verify import main as verify_main

    argv: list[str] = []
    if record:
        argv.append("--record")
    if skip_video:
        argv.append("--skip-video")
    if as_json:
        argv.append("--json")
    raise typer.Exit(code=verify_main(argv))


@app.command()
def run(
    port: int = typer.Option(None, help="Port (default: PORT from .env, 8765). The next free port is used if busy."),
    lan: bool = typer.Option(False, "--lan", help="Listen on all interfaces (hub mode / other devices)."),
    open_browser: bool = typer.Option(False, "--open-browser", help="Open the default browser."),
    role: str = typer.Option("standalone", help="standalone | bench | hub"),
    hub_url: str = typer.Option(None, help="Bench role: the hub's URL, e.g. http://192.168.1.20:8765"),
    bench_id: str = typer.Option(None, help="Bench label shown to the TA, e.g. B07"),
) -> None:
    """Start the bench (or hub) web app."""
    from polarity.server import serve

    if role not in ("standalone", "bench", "hub"):
        raise typer.BadParameter("role must be standalone, bench or hub")
    if role == "bench" and not hub_url:
        raise typer.BadParameter("--role bench needs --hub-url")
    serve(port=port, lan=lan or role == "hub", open_browser=open_browser, role=role, hub_url=hub_url,
          bench_id=bench_id, path="/ta" if role == "hub" else "/")


@app.command()
def devices(max_index: int = typer.Option(5, help="Highest camera index to probe.")) -> None:
    """List cameras that open (indices 0–5) and their resolution."""
    from rich.table import Table

    from polarity.edge.camera import probe_devices

    table = Table(title="Cameras")
    for col in ("Index", "Opens", "Resolution / error"):
        table.add_column(col)
    for d in probe_devices(max_index):
        table.add_row(str(d["index"]), "yes" if d["ok"] else "no", d.get("resolution") or d.get("error") or "")
    _console().print(table)
    _console().print("Set CAMERA_INDEX in .env to the camera above your board.")


@app.command()
def markers(out: Path = typer.Option(None, help="Output folder (default: assets/print).")) -> None:
    """Generate the printable ArUco marker mat (A4 PDF + PNG)."""
    from polarity.config import APP_NAME, get_config
    from polarity.edge.markers import write_mat

    target = out or (get_config().paths.root / "assets" / "print")
    pdf, png = write_mat(target, APP_NAME)
    _console().print(f"Wrote {pdf} and {png}. Print at 100% (Actual size) and check the 1 cm scale bar.")


@app.command("render-synthetic")
def render_synthetic(
    lab: str = typer.Option("lab1", help="Lab id (synthetic scenes exist for lab1)."),
    step: list[str] = typer.Option(None, help="Only these step ids (repeatable)."),
) -> None:
    """Render synthetic placeholder board images for demo mode and CI (never for accuracy claims)."""
    from polarity.config import get_config
    from polarity.demo.synthetic_board import render_all

    cfg = get_config()
    paths = render_all(cfg.paths.demo / lab, steps=step or None)
    _console().print(f"Rendered {len(paths)} synthetic scenes into {cfg.paths.demo / lab}")


@app.command("eval")
def eval_cmd(
    dataset: Path = typer.Option(None, help="Dataset folder (default: data/eval/<lab>, or data/demo/<lab> with --mock)."),
    limit: int = typer.Option(None, help="Only evaluate the first N images."),
    mock: bool = typer.Option(False, "--mock", help="Use canned model answers on the synthetic set (not evidence)."),
    lab: str = typer.Option(None, help="Lab id (default: DEFAULT_LAB)."),
) -> None:
    """Evaluate the check pipeline on labelled photos and write docs/EVAL_RESULTS.md (mock runs: data/eval_runs/)."""
    from rich.progress import Progress

    from polarity.config import get_config, reset_config
    from polarity.engine.evaluate import discover, run_eval, write_outputs
    from polarity.models.lab import load_lab

    if mock:
        os.environ["POLARITY_MOCK_MODELS"] = "1"
        os.environ.setdefault("POLARITY_MOCK_LATENCY_MS", "0")
        reset_config()
    cfg = get_config()
    console = _console()
    lab_id = lab or cfg.env.default_lab
    lab_def = load_lab(cfg.paths.labs / f"{lab_id}.yaml")
    if dataset is None:
        dataset = (cfg.paths.demo if mock else cfg.paths.eval) / lab_id
    if mock and not any(dataset.glob("*/*.png")):
        from polarity.demo.synthetic_board import render_all

        console.print("No demo images yet; rendering the synthetic set first.")
        render_all(dataset)
    if not mock and not cfg.mock and not cfg.api_key:
        console.print("[yellow]PENDING: needs NEBIUS_API_KEY.[/yellow] A real eval calls Token Factory. "
                      "Use --mock to exercise the harness on synthetic images.")
        raise typer.Exit(code=2)
    samples = discover(dataset, lab_def)
    if not samples:
        console.print(f"No labelled images found in {dataset}. Capture them with "
                      "`python -m polarity capture --lab lab1 --step s3 --label E_LED_REVERSED`.")
        raise typer.Exit(code=1)
    total = min(len(samples), limit) if limit else len(samples)
    with Progress(console=console) as progress:
        task = progress.add_task("Evaluating", total=total)
        summary, preds = run_eval(cfg, dataset, lab_def, limit=limit, mock=cfg.mock,
                                  progress=lambda i, n, p: progress.update(task, completed=i))
    outputs = write_outputs(summary, preds, cfg)

    def pct(x: float | None) -> str:
        return "n/a" if x is None else f"{100 * x:.1f}%"

    if summary.mock:
        console.print("[bold yellow]MOCK RUN: synthetic images + canned answers. Not accuracy evidence.[/bold yellow]")
    console.print(f"N={summary.n}  coverage={pct(summary.coverage)}  selective_acc={pct(summary.selective_accuracy)}  "
                  f"false_pass={pct(summary.false_pass_rate)}  error_id_hit={pct(summary.error_id_hit_rate)}")
    gate = {True: "MET", False: "NOT MET", None: "n/a"}[summary.gate_met]
    console.print(f"Decision gate (false-pass ≤ 5%, selective accuracy ≥ 85%): {gate}")
    for name, path in outputs.items():
        console.print(f"  {name}: {path}")


@app.command()
def purge(days: int = typer.Option(None, help="Retention in days (default: MEDIA_RETENTION_DAYS).")) -> None:
    """Delete stored bench media older than the retention period."""
    from polarity.config import get_config
    from polarity.storage.media import MediaStore

    cfg = get_config()
    removed = MediaStore(cfg.paths.media).purge(days if days is not None else cfg.env.media_retention_days)
    _console().print(f"Removed {removed} media files older than "
                     f"{days if days is not None else cfg.env.media_retention_days} days.")


def main() -> None:
    """Console-script entry point (``polarity``)."""
    app()


if __name__ == "__main__":
    main()
