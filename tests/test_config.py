"""Settings sources: ``.env``, then ``.env.local`` (later wins), with real environment variables winning over both."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_env_local_overrides_env_and_real_env_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from polarity import config, paths

    env = tmp_path / "team.env"
    env.write_text("PORT=1111\nCAMERA_INDEX=1\nTA_PIN=1111\n", encoding="utf-8")
    (tmp_path / "team.env.local").write_text("PORT=2222\nTA_PIN=2222\n", encoding="utf-8")
    monkeypatch.setenv("POLARITY_ENV_FILE", str(env))
    monkeypatch.setenv("TA_PIN", "3333")
    monkeypatch.delenv("PORT", raising=False)
    monkeypatch.delenv("CAMERA_INDEX", raising=False)
    config.reset_config()
    assert [p.name for p in paths.env_files()] == ["team.env", "team.env.local"]
    cfg = config.get_config()
    assert cfg.env.port == 2222                         # .env.local beats .env
    assert cfg.env.camera_index == 1                    # only set in .env
    assert cfg.env.ta_pin.get_secret_value() == "3333"  # a real environment variable beats both files


def test_env_local_alone_is_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from polarity import config, paths

    (tmp_path / "team.env.local").write_text("PORT=4444\n", encoding="utf-8")
    monkeypatch.setenv("POLARITY_ENV_FILE", str(tmp_path / "team.env"))  # .env itself does not exist
    monkeypatch.delenv("PORT", raising=False)
    config.reset_config()
    assert [p.name for p in paths.env_files()] == ["team.env.local"]
    assert config.get_config().env.port == 4444
