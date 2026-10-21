"""Small Pillow/numpy helpers shared by the verifier, the synthetic renderer and the web layer.

Only Pillow and numpy are imported here (no OpenCV) so Phase 0 can run with minimal dependencies.
"""

from __future__ import annotations

import base64
import io
from functools import lru_cache

import numpy as np
from PIL import Image, ImageFont

_FONT_CANDIDATES_REGULAR = (
    "DejaVuSans.ttf",
    "Arial.ttf",
    "arial.ttf",
    "Helvetica.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)
_FONT_CANDIDATES_BOLD = (
    "DejaVuSans-Bold.ttf",
    "Arial Bold.ttf",
    "arialbd.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


@lru_cache(maxsize=64)
def get_font(size: int, bold: bool = False) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """Return a scalable font of ``size`` px, falling back to Pillow's bundled font.

    Pillow >= 10.1 ships a scalable default font, so text renders at a readable size on every OS
    even when no system font is found.
    """
    candidates = _FONT_CANDIDATES_BOLD + _FONT_CANDIDATES_REGULAR if bold else _FONT_CANDIDATES_REGULAR
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # very old Pillow without the size argument
        return ImageFont.load_default()


def pil_to_bytes(img: Image.Image, fmt: str = "JPEG", quality: int = 85) -> bytes:
    """Encode a PIL image to bytes (JPEG or PNG)."""
    buf = io.BytesIO()
    if fmt.upper() == "JPEG":
        img.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
    else:
        img.save(buf, format=fmt.upper())
    return buf.getvalue()


def data_url(data: bytes, mime: str) -> str:
    """Return a base64 ``data:`` URL for ``data``."""
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def resize_long_side(img: Image.Image, max_long_side: int) -> Image.Image:
    """Downscale (never upscale) so the longer side is at most ``max_long_side`` pixels."""
    w, h = img.size
    long_side = max(w, h)
    if long_side <= max_long_side:
        return img
    scale = max_long_side / float(long_side)
    return img.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.LANCZOS)


def bgr_to_pil(arr: np.ndarray) -> Image.Image:
    """Convert an OpenCV-style BGR (or grey) uint8 array to a PIL RGB image."""
    if arr.ndim == 2:
        return Image.fromarray(arr).convert("RGB")
    return Image.fromarray(arr[:, :, ::-1].copy())


def pil_to_bgr(img: Image.Image) -> np.ndarray:
    """Convert a PIL image to an OpenCV-style BGR uint8 array."""
    rgb = np.asarray(img.convert("RGB"), dtype=np.uint8)
    return rgb[:, :, ::-1].copy()
