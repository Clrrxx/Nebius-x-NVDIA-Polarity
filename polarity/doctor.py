"""``python -m polarity doctor``: check this machine and print exact fixes.

FAIL only for blockers (Python version, missing packages, OpenCV without ArUco). Everything else (no key yet,
no camera, no capabilities.json, empty pricing, busy port, low disk) is a WARN with the fix, because demo mode
works without any of it.
"""

from __future__ import annotations

import importlib
import importlib.metadata as md
import shutil
import sys
from dataclasses import dataclass
from typing import Any

REQUIRED = ["openai", "dotenv", "pydantic", "pydantic_settings", "fastapi", "uvicorn", "jinja2", "multipart", "typer",
            "rich", "httpx", "numpy", "PIL", "cv2", "yaml", "markdown", "pypdfium2", "tavily"]


@dataclass
class Item:
    name: str
    status: str  # OK | WARN | FAIL | SKIP
    detail: str
    fix: str = ""


def camera_help() -> str:
    if sys.platform == "darwin":
        return ("macOS: System Settings → Privacy & Security → Camera, allow your terminal app (Terminal, iTerm, VS Code "
                "or Cursor), then restart it. Or set CAMERA_SOURCE=demo.")
    if sys.platform == "win32":
        return ("Windows: Settings → Privacy & security → Camera → turn on 'Let desktop apps access your camera'. "
                "Close other apps using the camera, or try CAMERA_INDEX=1. Or set CAMERA_SOURCE=demo.")
    return "Linux: check that /dev/video0 exists and your user is in the 'video' group. Or set CAMERA_SOURCE=demo."


def run_checks(skip_camera: bool = False, skip_network: bool = False) -> list[Item]:
    items: list[Item] = []
    v = sys.version_info
    if (v.major, v.minor) in ((3, 11), (3, 12)):
        items.append(Item("Python", "OK", f"{v.major}.{v.minor}.{v.micro}"))
    else:
        items.append(Item("Python", "FAIL", f"{v.major}.{v.minor} is not supported",
                          "Install Python 3.12 (macOS: brew install python@3.12 · Windows: winget install Python.Python.3.12) "
                          "and re-run the setup script."))
    missing = []
    for mod in REQUIRED:
        try:
            importlib.import_module(mod)
        except ImportError:
            missing.append(mod)
    items.append(Item("Packages", "FAIL" if missing else "OK", ", ".join(missing) or "all importable",
                      "Re-run the setup script (or pip install -r requirements.txt)." if missing else ""))
    try:
        import cv2

        has_aruco = hasattr(cv2, "aruco") and hasattr(cv2.aruco, "ArucoDetector")
        dists = {d.metadata["Name"].lower() for d in md.distributions() if d.metadata["Name"]}
        clash = sorted(dists & {"opencv-python", "opencv-python-headless", "opencv-contrib-python-headless"})
        if not has_aruco:
            items.append(Item("OpenCV ArUco", "FAIL", f"cv2 {cv2.__version__} without cv2.aruco",
                              "pip uninstall -y opencv-python opencv-python-headless && pip install opencv-contrib-python"))
        elif clash and "opencv-contrib-python" in dists:
            items.append(Item("OpenCV ArUco", "WARN", f"also installed: {', '.join(clash)} (they conflict)",
                              f"pip uninstall -y {' '.join(clash)} && pip install --force-reinstall opencv-contrib-python"))
        else:
            items.append(Item("OpenCV ArUco", "OK", f"cv2 {cv2.__version__}"))
    except ImportError:
        pass

    from polarity.config import get_config
    from polarity.llm.client import mask_secret

    cfg = get_config()
    env_path = cfg.paths.root / ".env"
    if cfg.api_key:
        items.append(Item("NEBIUS_API_KEY", "OK", mask_secret(cfg.api_key)))
    else:
        items.append(Item("NEBIUS_API_KEY", "WARN", "not set (mock/demo mode still works)",
                          f"Copy .env.example to .env ({env_path}) and paste your Token Factory key."))
    if cfg.api_key and not skip_network:
        items.append(_token_factory(cfg))
    else:
        items.append(Item("Token Factory", "SKIP", "no key" if not cfg.api_key else "skipped"))
    if cfg.capabilities.verified:
        caps = cfg.capabilities
        items.append(Item("capabilities.json", "OK", f"perception={caps.models['perception'].id}, "
                                                     f"combined image+audio={caps.combined_image_audio}"))
    else:
        items.append(Item("capabilities.json", "WARN", "missing", "Run: python -m polarity verify"))
    items.append(Item("Pricing", "OK" if cfg.prices else "WARN",
                      f"{len(cfg.prices)} model prices" if cfg.prices else "config/pricing.yaml is empty: cost shows n/a",
                      "" if cfg.prices else "Copy real prices from the Token Factory console into config/pricing.yaml "
                                            "so the budget guard can work."))
    items.append(Item("Tavily", "OK" if cfg.tavily_key else "SKIP",
                      mask_secret(cfg.tavily_key) if cfg.tavily_key else "no TAVILY_API_KEY (part lookup hidden)"))
    if skip_camera or cfg.env.camera_source == "demo":
        items.append(Item("Camera", "SKIP", "demo camera" if cfg.env.camera_source == "demo" else "skipped"))
    else:
        items.append(_camera(cfg))
    from polarity.server import find_free_port, port_is_free

    port = cfg.env.port
    if port_is_free("127.0.0.1", port):
        items.append(Item("Port", "OK", f"{port} is free"))
    else:
        items.append(Item("Port", "WARN", f"{port} is busy; `polarity run` will use {find_free_port('127.0.0.1', port)}",
                          "Or set PORT in .env."))
    free_gb = shutil.disk_usage(cfg.paths.data if cfg.paths.data.exists() else cfg.paths.root).free / 1e9
    items.append(Item("Disk", "OK" if free_gb >= 1 else "WARN", f"{free_gb:.1f} GB free for media",
                      "" if free_gb >= 1 else "Free some space or lower MEDIA_RETENTION_DAYS and run: python -m polarity purge"))
    demo = cfg.paths.demo / "lab1"
    has_demo = demo.exists() and any(demo.glob("*/*.png"))
    items.append(Item("Demo scenes", "OK" if has_demo else "WARN", "rendered" if has_demo else "not rendered yet",
                      "" if has_demo else "python -m polarity render-synthetic (also happens on first demo start)"))
    mat = cfg.paths.root / "assets" / "print" / "marker_mat_A4.pdf"
    items.append(Item("Marker mat", "OK" if mat.exists() else "WARN", str(mat.name) if mat.exists() else "missing",
                      "" if mat.exists() else "python -m polarity markers"))
    return items


def _token_factory(cfg: Any) -> Item:
    import openai

    from polarity.llm.client import make_client

    base = cfg.base_url
    if not base:
        return Item("Token Factory", "WARN", "no base URL yet", "Run: python -m polarity verify")
    try:
        n = len(list(make_client(base, cfg.api_key, timeout=10.0).models.list(timeout=10.0)))
        return Item("Token Factory", "OK", f"{base} ({n} models)")
    except openai.AuthenticationError:
        return Item("Token Factory", "FAIL", "key rejected (401)", "Check NEBIUS_API_KEY in .env.")
    except (openai.APIStatusError, openai.APIConnectionError) as exc:
        return Item("Token Factory", "WARN", f"unreachable: {type(exc).__name__}", "Check your network / proxy.")


def _camera(cfg: Any) -> Item:
    from polarity.edge.camera import open_capture

    cap, err = open_capture(cfg.env.camera_index, cfg.env.camera_width, cfg.env.camera_height)
    if cap is None:
        return Item("Camera", "WARN", f"index {cfg.env.camera_index}: {err}", camera_help())
    import cv2

    w, h = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    cap.release()
    return Item("Camera", "OK", f"index {cfg.env.camera_index} opens at {w}x{h}")


def main(skip_camera: bool = False, skip_network: bool = False) -> int:
    from rich.console import Console
    from rich.table import Table

    console = Console()
    items = run_checks(skip_camera, skip_network)
    table = Table(title="Polarity doctor")
    for col in ("Check", "Status", "Details", "Fix"):
        table.add_column(col, overflow="fold")
    colours = {"OK": "green", "WARN": "yellow", "FAIL": "red", "SKIP": "cyan"}
    for it in items:
        table.add_row(it.name, f"[{colours[it.status]}]{it.status}[/{colours[it.status]}]", it.detail, it.fix)
    console.print(table)
    failed = [i for i in items if i.status == "FAIL"]
    if failed:
        console.print(f"[red]{len(failed)} blocking problem(s): fix them and run doctor again.[/red]")
        return 1
    console.print("Ready. Start with:  python -m polarity run --open-browser   (demo: CAMERA_SOURCE=demo, "
                  "POLARITY_MOCK_MODELS=1)")
    return 0
