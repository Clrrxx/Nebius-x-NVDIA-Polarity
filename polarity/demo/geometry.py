"""Physical geometry (millimetres) of the printed marker mat and a half-size (400-point) breadboard.

Mat coordinates: origin at the mat's INNER top-left corner (the inner corner of ArUco marker 0), x right, y down.
The board locator warps this 120 × 90 mm rectangle (4:3) to 1024 × 768 px, i.e. ~8.5 px per mm.

Breadboard layout (top to bottom): − rail (blue line above it), + rail (red line below it), rows a–e,
centre channel, rows f–j, + rail (red line), − rail (blue line). 30 numbered columns at 2.54 mm pitch; rails
have 25 holes in five groups of five aligned with columns 1–5, 7–11, 13–17, 19–23, 25–29.
"""

from __future__ import annotations

MAT_W_MM = 120.0
MAT_H_MM = 90.0
MARKER_MM = 30.0
MARKER_IDS = (0, 1, 2, 3)  # top-left, top-right, bottom-right, bottom-left (DICT_4X4_50)

BOARD_W_MM = 82.5
BOARD_H_MM = 55.0
BOARD_X_MM = (MAT_W_MM - BOARD_W_MM) / 2
BOARD_Y_MM = (MAT_H_MM - BOARD_H_MM) / 2
PITCH = 2.54
N_COLS = 30
COL_MARGIN = (BOARD_W_MM - (N_COLS - 1) * PITCH) / 2

# Row centre y, relative to the board's top edge.
_ROW_Y = {
    "T-": 5.91, "T+": 8.45,
    "a": 13.53, "b": 16.07, "c": 18.61, "d": 21.15, "e": 23.69,
    "f": 31.31, "g": 33.85, "h": 36.39, "i": 38.93, "j": 41.47,
    "B+": 46.55, "B-": 49.09,
}
RAIL_ROWS = ("T-", "T+", "B+", "B-")
STRIP_ROWS = tuple("abcdefghij")
RAIL_COLS = tuple(c for c in range(1, N_COLS) if c % 6 != 0)  # 1-5, 7-11, 13-17, 19-23, 25-29
CHANNEL_Y = (_ROW_Y["e"] + _ROW_Y["f"]) / 2

# Rail marking lines (relative to board top): blue above the outer − rails, red beside the inner + rails.
LINE_Y = {"top_blue": _ROW_Y["T-"] - 1.9, "top_red": _ROW_Y["T+"] + 1.9,
          "bottom_red": _ROW_Y["B+"] - 1.9, "bottom_blue": _ROW_Y["B-"] + 1.9}


def col_x(col: float) -> float:
    """Mat x (mm) of a column centre (1-based, fractional allowed)."""
    return BOARD_X_MM + COL_MARGIN + (col - 1) * PITCH


def row_y(row: str) -> float:
    """Mat y (mm) of a row centre."""
    return BOARD_Y_MM + _ROW_Y[row]


def hole(row: str, col: float) -> tuple[float, float]:
    """Mat (x, y) in mm of the hole at ``row``/``col``."""
    return col_x(col), row_y(row)


def line_y(name: str) -> float:
    return BOARD_Y_MM + LINE_Y[name]


def channel_y() -> float:
    return BOARD_Y_MM + CHANNEL_Y


def all_holes() -> list[tuple[str, int]]:
    holes = [(r, c) for r in STRIP_ROWS for c in range(1, N_COLS + 1)]
    holes += [(r, c) for r in RAIL_ROWS for c in RAIL_COLS]
    return holes
