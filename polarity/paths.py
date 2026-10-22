"""Filesystem locations (standard library only, so the light Phase 0 script can use them).

Overrides (all optional):
- ``POLARITY_HOME``: repository root (defaults to the folder containing the ``polarity`` package);
- ``POLARITY_DATA_DIR``: runtime data folder (defaults to ``<root>/data``); tests point this at a temp dir;
- ``POLARITY_ENV_FILE``: the dotenv file to read (defaults to ``<root>/.env``; a sibling ``.env.local`` overrides it);
- ``POLARITY_DOCS_DIR``: where generated reports are written (defaults to ``<root>/docs``);
- ``POLARITY_LABS_DIR``: published lab YAML files (defaults to ``<root>/labs``).
"""

from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    """Repository root (works for ``pip install -e .`` and for running from a checkout)."""
    override = os.environ.get("POLARITY_HOME")
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def data_dir() -> Path:
    override = os.environ.get("POLARITY_DATA_DIR")
    return Path(override).expanduser().resolve() if override else repo_root() / "data"


def env_file() -> Path:
    override = os.environ.get("POLARITY_ENV_FILE")
    return Path(override).expanduser().resolve() if override else repo_root() / ".env"


def env_files() -> list[Path]:
    """Dotenv files that exist, in load order: ``.env`` then ``.env.local`` (later files override earlier ones;
    real environment variables override both)."""
    base = env_file()
    return [p for p in (base, base.with_name(base.name + ".local")) if p.exists()]


def docs_dir() -> Path:
    override = os.environ.get("POLARITY_DOCS_DIR")  # tests redirect generated reports here
    return Path(override).expanduser().resolve() if override else repo_root() / "docs"


def config_dir() -> Path:
    return repo_root() / "config"


def labs_dir() -> Path:
    override = os.environ.get("POLARITY_LABS_DIR")  # tests publish compiled labs into a temp copy
    return Path(override).expanduser().resolve() if override else repo_root() / "labs"


def capabilities_file() -> Path:
    return data_dir() / "capabilities.json"
