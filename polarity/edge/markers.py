"""Printable ArUco marker mat (A4 portrait, 300 dpi): ``python -m polarity markers``.

Four DICT_4X4_50 markers, IDs 0 (top-left), 1 (top-right), 2 (bottom-right), 3 (bottom-left), each 30 mm,
placed so their inner corners are the corners of a 120 × 90 mm rectangle that holds a half-size breadboard.
Includes a 1 cm scale bar to verify the print size.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

from polarity.demo import geometry as g
from polarity.imaging import get_font

DPI = 300
A4_MM = (210.0, 297.0)
INNER_ORIGIN_MM = ((A4_MM[0] - g.MAT_W_MM) / 2, 45.0)  # inner rectangle top-left on the page


def mm(v: float) -> int:
    return int(round(v * DPI / 25.4))


def marker_image(marker_id: int, side_px: int) -> np.ndarray:
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    return cv2.aruco.generateImageMarker(dictionary, marker_id, side_px)


def _dashed_rect(d: ImageDraw.ImageDraw, box: tuple[int, int, int, int], dash: int, gap: int, fill: tuple[int, int, int],
                 width: int) -> None:
    x0, y0, x1, y1 = box
    for x in range(x0, x1, dash + gap):
        d.line((x, y0, min(x + dash, x1), y0), fill=fill, width=width)
        d.line((x, y1, min(x + dash, x1), y1), fill=fill, width=width)
    for y in range(y0, y1, dash + gap):
        d.line((x0, y, x0, min(y + dash, y1)), fill=fill, width=width)
        d.line((x1, y, x1, min(y + dash, y1)), fill=fill, width=width)


def render_mat(app_name: str = "Polarity") -> Image.Image:
    """Render the A4 mat as a 300 dpi PIL image."""
    page = Image.new("RGB", (mm(A4_MM[0]), mm(A4_MM[1])), (255, 255, 255))
    d = ImageDraw.Draw(page)
    ox, oy = INNER_ORIGIN_MM
    side = mm(g.MARKER_MM)
    # Marker k sits outside inner corner k so that its inner corner touches the rectangle corner.
    offsets = [(-g.MARKER_MM, -g.MARKER_MM), (g.MAT_W_MM, -g.MARKER_MM), (g.MAT_W_MM, g.MAT_H_MM), (-g.MARKER_MM, g.MAT_H_MM)]
    for marker_id, (dx, dy) in zip(g.MARKER_IDS, offsets, strict=True):
        tile = Image.fromarray(marker_image(marker_id, side)).convert("RGB")
        page.paste(tile, (mm(ox + dx), mm(oy + dy)))
        label_y = mm(oy + dy) - mm(5) if dy < 0 else mm(oy + dy + g.MARKER_MM) + mm(1.5)  # outside the mat area
        d.text((mm(ox + dx) + 4, label_y), f"ID {marker_id}", fill=(120, 120, 120), font=get_font(28))
    inset = 2.0  # keep guide lines off the markers' corners (ArUco needs a clean quiet zone)
    _dashed_rect(d, (mm(ox + inset), mm(oy + inset), mm(ox + g.MAT_W_MM - inset), mm(oy + g.MAT_H_MM - inset)),
                 mm(3), mm(2), (150, 150, 150), 3)
    bx, by = ox + g.BOARD_X_MM, oy + g.BOARD_Y_MM
    _dashed_rect(d, (mm(bx), mm(by), mm(bx + g.BOARD_W_MM), mm(by + g.BOARD_H_MM)), mm(1), mm(1.5), (190, 190, 190), 2)
    d.text((mm(bx) + 10, mm(by) + 10), "half-size breadboard here", fill=(175, 175, 175), font=get_font(30))

    y = oy + g.MAT_H_MM + g.MARKER_MM + 14
    d.text((mm(15), mm(y)), f"{app_name} marker mat", fill=(20, 20, 20), font=get_font(64, bold=True))
    lines = [
        "1. Print at 100% / \"Actual size\" (no fit-to-page). The bar below must measure exactly 1 cm.",
        "2. Tape the mat flat on the bench and keep the breadboard inside the dashed rectangle.",
        "3. Mount the camera 25-35 cm above, looking straight down, so all four markers are visible.",
        "Markers: ArUco DICT_4X4_50, IDs 0 (top-left), 1 (top-right), 2 (bottom-right), 3 (bottom-left), 30 mm each.",
        "Safety: batteries and USB power only. Never mains. If anything gets hot, smells or smokes: switch off, call the TA.",
    ]
    font = get_font(34)
    for i, text in enumerate(lines):
        d.text((mm(15), mm(y + 12 + i * 7)), text, fill=(40, 40, 40), font=font)
    sy = y + 12 + len(lines) * 7 + 6
    x0 = mm(15)
    d.rectangle((x0, mm(sy), x0 + mm(10), mm(sy) + mm(2)), fill=(0, 0, 0))
    for t in (0, 5, 10):
        d.line((x0 + mm(t), mm(sy) - mm(1.5), x0 + mm(t), mm(sy) + mm(3.5)), fill=(0, 0, 0), width=3)
    d.text((x0 + mm(13), mm(sy) - mm(1)), "1 cm scale bar: check with a ruler", fill=(40, 40, 40), font=get_font(34))
    return page


def write_mat(out_dir: Path, app_name: str = "Polarity") -> tuple[Path, Path]:
    """Write ``marker_mat_A4.pdf`` and ``marker_mat_A4.png`` into ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    page = render_mat(app_name)
    pdf = out_dir / "marker_mat_A4.pdf"
    png = out_dir / "marker_mat_A4.png"
    page.save(pdf, "PDF", resolution=float(DPI))
    page.save(png, "PNG", dpi=(DPI, DPI))
    return pdf, png
