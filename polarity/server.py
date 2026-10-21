"""Run the web server (``python -m polarity run``): free-port selection, LAN binding, browser opening."""

from __future__ import annotations

import socket
import threading
import time
import webbrowser

from rich.console import Console


def port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def find_free_port(host: str, start: int, attempts: int = 25) -> int:
    for port in range(start, start + attempts):
        if port_is_free(host, port):
            return port
    raise RuntimeError(f"No free port between {start} and {start + attempts - 1}.")


def lan_ip() -> str | None:
    """Best-effort LAN address for hub mode instructions (no packets are sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("10.255.255.255", 1))
            return str(sock.getsockname()[0])
    except OSError:
        return None


def serve(port: int | None = None, lan: bool = False, open_browser: bool = False, role: str = "standalone",
          hub_url: str | None = None, bench_id: str | None = None, path: str = "/") -> None:
    import uvicorn

    from polarity.config import APP_NAME, get_config
    from polarity.logging_setup import register_secret, setup_logging
    from polarity.runtime import Runtime
    from polarity.web.app import create_app

    console = Console()
    cfg = get_config()
    setup_logging(cfg.paths.logs)
    register_secret(cfg.api_key)
    register_secret(cfg.tavily_key)
    cfg.role_override = role
    cfg.hub_url = hub_url
    cfg.bench_id = bench_id
    host = "0.0.0.0" if lan else "127.0.0.1"
    wanted = port or cfg.env.port
    chosen = find_free_port(host, wanted)
    if chosen != wanted:
        console.print(f"Port {wanted} is busy; using {chosen}.")
    rt = Runtime(cfg)
    app = create_app(rt)
    url = f"http://127.0.0.1:{chosen}{path}"
    console.rule(f"{APP_NAME}")
    console.print(f"Open [bold]{url}[/bold]   (TA dashboard: /ta · Debug: /debug)")
    if lan:
        ip = lan_ip()
        console.print(f"LAN address: http://{ip or '<this-computer-ip>'}:{chosen}")
    if cfg.mock:
        console.print("[bold yellow]MOCK MODE: canned model answers, not real AI output.[/bold yellow]")
    elif not cfg.api_key:
        console.print("[yellow]No NEBIUS_API_KEY: checks will fail until you add it to .env "
                      "(or run with POLARITY_MOCK_MODELS=1).[/yellow]")
    elif not cfg.capabilities.verified:
        console.print("[yellow]data/capabilities.json missing: run `python -m polarity verify` first.[/yellow]")
    console.print(f"Camera: {cfg.env.camera_source}  ·  role: {role}  ·  Ctrl+C to stop")
    if open_browser:
        def _open() -> None:
            time.sleep(1.2)
            webbrowser.open(url)

        threading.Thread(target=_open, daemon=True).start()
    config = uvicorn.Config(app, host=host, port=chosen, log_level="warning", timeout_graceful_shutdown=2,
                            ws_ping_interval=20)
    uvicorn.Server(config).run()
