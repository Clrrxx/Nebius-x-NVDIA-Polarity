"""Command-line interface (Typer). Every command also works as ``python -m polarity <command>``."""

from __future__ import annotations

import typer

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Polarity: an AI lab partner for breadboard labs (Nebius Token Factory + NVIDIA Nemotron).",
)


@app.callback()
def _root() -> None:
    """Polarity command line. Run a command with --help for its options."""


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


def main() -> None:
    """Console-script entry point (``polarity``)."""
    app()


if __name__ == "__main__":
    main()
