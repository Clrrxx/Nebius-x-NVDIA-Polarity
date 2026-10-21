"""Logging: rich console output plus a rotating file in ``data/logs``. Secrets are masked in every record
and HTTP client loggers stay at WARNING so request headers are never logged.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

_SECRETS: set[str] = set()


def register_secret(value: str | None) -> None:
    """Remember a secret so it is masked in all log output."""
    if value and len(value) >= 8:
        _SECRETS.add(value)


class _MaskSecrets(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if _SECRETS:
            msg = record.getMessage()
            masked = msg
            for secret in _SECRETS:
                masked = masked.replace(secret, "****" + secret[-4:])
            if masked != msg:
                record.msg, record.args = masked, ()
        return True


def setup_logging(log_dir: Path | None = None, level: int = logging.INFO) -> None:
    """Configure root logging once (idempotent)."""
    root = logging.getLogger()
    if getattr(root, "_polarity_configured", False):
        return
    root.setLevel(level)
    try:
        from rich.logging import RichHandler

        console: logging.Handler = RichHandler(rich_tracebacks=False, show_path=False, markup=False)
    except ImportError:
        console = logging.StreamHandler()
    console.addFilter(_MaskSecrets())
    root.addHandler(console)
    if log_dir is not None:
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            fh = logging.handlers.RotatingFileHandler(log_dir / "polarity.log", maxBytes=2_000_000, backupCount=3,
                                                      encoding="utf-8")
            fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
            fh.addFilter(_MaskSecrets())
            root.addHandler(fh)
        except OSError:
            pass
    for noisy in ("httpx", "httpcore", "openai", "urllib3", "multipart", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    root._polarity_configured = True  # type: ignore[attr-defined]
