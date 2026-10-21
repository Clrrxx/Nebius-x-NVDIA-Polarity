"""Local media store under ``data/media/<session_id>/``. Images and audio never leave the bench except the
checked frame (and optional voice clip) sent to Token Factory at check time.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

import cv2
import numpy as np

from polarity.cvio import imwrite


class MediaStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str, name: str) -> Path:
        folder = self.root / session_id
        folder.mkdir(parents=True, exist_ok=True)
        return folder / name

    def save_image(self, session_id: str, name: str, img: np.ndarray, quality: int = 88) -> str:
        """Save a BGR image as JPEG; returns the path relative to the media root (POSIX style)."""
        path = self._path(session_id, name)
        imwrite(path, img, [cv2.IMWRITE_JPEG_QUALITY, quality])
        return path.relative_to(self.root).as_posix()

    def save_bytes(self, session_id: str, name: str, data: bytes) -> str:
        path = self._path(session_id, name)
        path.write_bytes(data)
        return path.relative_to(self.root).as_posix()

    def resolve(self, rel: str) -> Path | None:
        """Absolute path for a stored file, or ``None`` if it escapes the media root or does not exist."""
        try:
            path = (self.root / rel).resolve()
            path.relative_to(self.root.resolve())
        except (ValueError, OSError):
            return None
        return path if path.is_file() else None

    def purge(self, retention_days: int) -> int:
        """Delete session folders whose newest file is older than ``retention_days``. Returns files removed."""
        cutoff = time.time() - retention_days * 86400
        removed = 0
        if not self.root.exists():
            return 0
        for folder in self.root.iterdir():
            if not folder.is_dir():
                continue
            files = [f for f in folder.rglob("*") if f.is_file()]
            newest = max((f.stat().st_mtime for f in files), default=0)
            if newest < cutoff:
                removed += len(files)
                shutil.rmtree(folder, ignore_errors=True)
        return removed
