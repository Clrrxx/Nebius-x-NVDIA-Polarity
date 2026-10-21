"""Shared test setup: every test runs in mock/demo mode, offline, against temp data/docs folders."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point data/docs/.env at a temp dir and force mock models + demo camera, with no secrets."""
    data = tmp_path / "data"
    docs = tmp_path / "docs"
    data.mkdir()
    docs.mkdir()
    monkeypatch.setenv("POLARITY_DATA_DIR", str(data))
    monkeypatch.setenv("POLARITY_DOCS_DIR", str(docs))
    monkeypatch.setenv("POLARITY_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.setenv("POLARITY_MOCK_MODELS", "1")
    monkeypatch.setenv("POLARITY_MOCK_LATENCY_MS", "0")
    monkeypatch.setenv("CAMERA_SOURCE", "demo")
    for var in ("NEBIUS_API_KEY", "NEBIUS_BASE_URL", "TAVILY_API_KEY", "POLARITY_MODEL_PERCEPTION",
                "POLARITY_MODEL_FAST_TEXT", "POLARITY_MODEL_REASONING", "POLARITY_MODEL_DEEP", "AUDIO_MODE"):
        monkeypatch.delenv(var, raising=False)
    try:
        from polarity import config

        config.reset_config()
    except ImportError:
        pass
    yield tmp_path
    try:
        from polarity import config

        config.reset_config()
    except ImportError:
        pass


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@pytest.fixture
def fake_token_factory() -> Iterator[str]:
    """Run the fake Token Factory on a free localhost port; yields its base URL."""
    import uvicorn

    from tests.fake_token_factory import create_app

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning",
                                           lifespan="off"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 15
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    assert server.started, "fake Token Factory did not start"
    yield f"http://127.0.0.1:{port}/v1/"
    server.should_exit = True
    thread.join(timeout=5)


_SCENE_CACHE: dict[tuple[str, str], object] = {}


@pytest.fixture(scope="session")
def scene():  # noqa: ANN201 - returns a cached renderer
    """``scene(step, label)`` → synthetic BGR frame (rendered once per test session)."""
    from polarity.demo.synthetic_board import render_scene

    def _get(step: str, label: str):  # noqa: ANN202
        key = (step, label)
        if key not in _SCENE_CACHE:
            _SCENE_CACHE[key] = render_scene(step, label)
        return _SCENE_CACHE[key].copy()  # type: ignore[attr-defined]

    return _get
