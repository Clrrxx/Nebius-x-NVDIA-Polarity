"""Unicode-safe image file I/O for OpenCV.

``cv2.imread``/``cv2.imwrite`` fail silently on Windows when the path contains non-ASCII characters (for example a
user folder named "Zoë"). Encoding/decoding in memory and using Python's file I/O works on every OS.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def imread(path: Path | str, flags: int = cv2.IMREAD_COLOR) -> np.ndarray | None:
    """Read an image; ``None`` if the file is missing or not an image."""
    try:
        data = np.fromfile(str(path), dtype=np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, flags)


def imwrite(path: Path | str, img: np.ndarray, params: list[int] | None = None) -> bool:
    """Write an image (format from the extension); returns success."""
    ext = Path(path).suffix or ".png"
    ok, buf = cv2.imencode(ext, img, params or [])
    if not ok:
        return False
    Path(path).write_bytes(buf.tobytes())
    return True
