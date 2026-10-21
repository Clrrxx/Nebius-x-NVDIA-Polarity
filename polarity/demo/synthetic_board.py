"""Synthetic placeholder board images for demo mode, UI development and CI.

``python -m polarity render-synthetic`` draws a top-down breadboard on the marker mat (with real ArUco markers and
a mild camera perspective) for every Lab 1 step and every common error, plus special scenes used to demo the
quality gate and honest uncertainty. Saved to ``data/demo/lab1/<step>/<label>.png``.

THESE IMAGES MUST NEVER BE USED FOR ACCURACY CLAIMS. Real results come only from team photos in data/eval/.

Labels: ``correct``; an error id (``E_*``); ``_empty`` (s1 start); quality scenes ``_dark``, ``_blur``, ``_glare``,
``_markers``; ``_hand`` (hands cover the board); ``_partial`` (s3/s4: a fine detail is in shadow).
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

from polarity.demo import geometry as g
from polarity.imaging import get_font

SS = 16.0                      # supersampled px per mm
OUT_SCALE = 8.0                # final mat-space px per mm
X0, Y0 = -40.0, -40.0          # mat-space canvas origin (mm)
W_MM, H_MM = 200.0, 170.0
FRAME_SIZE = (1920, 1080)

DESK = (96, 82, 70)
PAPER = (186, 186, 180)
BOARD = (204, 200, 190)
BOARD_EDGE = (150, 146, 136)
CHANNEL = (184, 180, 170)
HOLE = (58, 58, 60)
RED_LINE = (200, 42, 42)
BLUE_LINE = (42, 82, 196)
LABEL = (110, 108, 104)
SKIN = (214, 166, 134)
SKIN_EDGE = (170, 122, 96)

QUALITY_LABELS = ("_dark", "_blur", "_glare", "_markers", "_hand")
SYNTHETIC_MANIFEST = "synthetic_manifest.json"

Hole = tuple[str, float]


@dataclass(frozen=True)
class Lead:
    colour: str
    to: Hole


@dataclass(frozen=True)
class Resistor:
    a: Hole
    b: Hole


@dataclass(frozen=True)
class Led:
    anode: Hole
    cathode: Hole
    lit: bool = False


@dataclass(frozen=True)
class Button:
    legs: tuple[Hole, Hole, Hole, Hole]
    rotated: bool = False


@dataclass(frozen=True)
class Jumper:
    a: Hole
    b: Hole
    colour: str = "black"


@dataclass(frozen=True)
class Finger:
    over: Hole


@dataclass
class Scene:
    parts: list[object] = field(default_factory=list)
    shadow_over: Hole | None = None
    hand: bool = False
    cover_markers: bool = False


CORRECT: dict[str, list[object]] = {
    "s1": [Lead("red", ("T+", 1)), Lead("black", ("T-", 1))],
    "s2": [Resistor(("T+", 8), ("b", 10))],
    "s3": [Led(("d", 10), ("d", 11))],
    "s4": [Button((("e", 11), ("e", 13), ("f", 11), ("f", 13)))],
    "s5": [Jumper(("a", 13), ("T-", 14))],
    "s6": [Finger(("f", 12))],
}
ERRORS: dict[str, dict[str, list[object]]] = {
    "s1": {"E_RAILS_SWAPPED": [Lead("red", ("T-", 1)), Lead("black", ("T+", 1))],
           "E_LEAD_IN_STRIP": [Lead("red", ("a", 2)), Lead("black", ("T-", 1))],
           "E_SAME_RAIL": [Lead("red", ("T+", 1)), Lead("black", ("T+", 3))]},
    "s2": {"E_RES_SHORTED": [Resistor(("a", 10), ("d", 10))],
           "E_RES_IN_MINUS": [Resistor(("T-", 8), ("b", 10))],
           "E_RES_BOTH_IN_STRIPS": [Resistor(("b", 6), ("b", 10))]},
    "s3": {"E_LED_REVERSED": [Led(("d", 11), ("d", 10))],
           "E_LED_SAME_STRIP": [Led(("c", 10), ("e", 10))],
           "E_LED_NOT_CONNECTED": [Led(("d", 15), ("d", 16))]},
    "s4": {"E_BTN_NOT_STRADDLING": [Button((("f", 11), ("f", 13), ("i", 11), ("i", 13)))],
           "E_BTN_WRONG_STRIP": [Button((("e", 14), ("e", 16), ("f", 14), ("f", 16)))],
           "E_BTN_ROTATED": [Button((("e", 11), ("e", 13), ("f", 11), ("f", 13)), rotated=True)]},
    "s5": {"E_GND_TO_PLUS": [Jumper(("a", 13), ("T+", 14))],
           "E_GND_WRONG_STRIP": [Jumper(("a", 15), ("T-", 14))]},
    "s6": {"E_NO_LIGHT": [Finger(("f", 12))]},
}
STEPS = ("s1", "s2", "s3", "s4", "s5", "s6")


def scene_labels(step: str) -> list[str]:
    labels = ["correct", *ERRORS.get(step, {}).keys(), *QUALITY_LABELS]
    if step in ("s3", "s4"):
        labels.append("_partial")
    if step == "s1":
        labels.append("_empty")
    return labels


def build_scene(step: str, label: str) -> Scene:
    """Cumulative parts: every earlier step done correctly, then this step's variant."""
    idx = STEPS.index(step)
    parts: list[object] = []
    for prev in STEPS[:idx]:
        parts += [p for p in CORRECT[prev] if not isinstance(p, Finger)]
    if label == "_empty":
        return Scene([])
    if label.startswith("E_"):
        parts += ERRORS[step][label]
    else:
        parts += CORRECT[step]
    if step == "s6":
        parts = [replace(p, lit=(label not in ("E_NO_LIGHT",))) if isinstance(p, Led) else p for p in parts]
    scene = Scene(parts)
    if label == "_partial":
        scene.shadow_over = ("d", 10.5) if step == "s3" else ("e", 12)
    if label == "_hand":
        scene.hand = True
    if label == "_markers":
        scene.cover_markers = True
    return scene


# ── drawing helpers (supersampled mat space) ─────────────────────────────────────────────────

def _px(x: float, y: float) -> tuple[float, float]:
    return (x - X0) * SS, (y - Y0) * SS


def _hole_px(h: Hole) -> tuple[float, float]:
    return _px(*g.hole(h[0], h[1]))


def _line(d: ImageDraw.ImageDraw, a: tuple[float, float], b: tuple[float, float], width_mm: float,
          fill: tuple[int, int, int]) -> None:
    w = max(1, int(width_mm * SS))
    d.line([a, b], fill=fill, width=w)
    r = w / 2
    for p in (a, b):
        d.ellipse((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=fill)


def _rot_rect(cx: float, cy: float, length: float, width: float, angle: float) -> list[tuple[float, float]]:
    ca, sa = math.cos(angle), math.sin(angle)
    pts = []
    for dx, dy in ((-length / 2, -width / 2), (length / 2, -width / 2), (length / 2, width / 2), (-length / 2, width / 2)):
        pts.append((cx + dx * ca - dy * sa, cy + dx * sa + dy * ca))
    return pts


def _pin(d: ImageDraw.ImageDraw, p: tuple[float, float]) -> None:
    r = 0.55 * SS
    d.rectangle((p[0] - r, p[1] - r, p[0] + r, p[1] + r), fill=(150, 150, 155))


def _draw_board(d: ImageDraw.ImageDraw) -> None:
    bx0, by0 = _px(g.BOARD_X_MM, g.BOARD_Y_MM)
    bx1, by1 = _px(g.BOARD_X_MM + g.BOARD_W_MM, g.BOARD_Y_MM + g.BOARD_H_MM)
    d.rounded_rectangle((bx0, by0, bx1, by1), radius=2.0 * SS, fill=BOARD, outline=BOARD_EDGE, width=int(0.4 * SS))
    cy = g.channel_y()
    d.rectangle((bx0 + 0.8 * SS, _px(0, cy - 1.2)[1], bx1 - 0.8 * SS, _px(0, cy + 1.2)[1]), fill=CHANNEL)
    for name, colour in (("top_blue", BLUE_LINE), ("top_red", RED_LINE), ("bottom_red", RED_LINE),
                         ("bottom_blue", BLUE_LINE)):
        y = _px(0, g.line_y(name))[1]
        d.line((bx0 + 2.0 * SS, y, bx1 - 2.0 * SS, y), fill=colour, width=int(0.45 * SS))
    r = 0.5 * SS
    for row, col in g.all_holes():
        x, y = _hole_px((row, col))
        d.rectangle((x - r, y - r, x + r, y + r), fill=HOLE)
    font = get_font(int(1.5 * SS))
    for col in (1, 5, 10, 15, 20, 25, 30):
        x = _px(g.col_x(col), 0)[0]
        for row, dy in (("a", -2.6), ("j", 1.3)):
            y = _px(0, g.row_y(row) + dy)[1]
            text = str(col)
            tw = d.textlength(text, font=font)
            d.text((x - tw / 2, y), text, fill=LABEL, font=font)
    for row in g.STRIP_ROWS:
        y = _px(0, g.row_y(row) - 0.8)[1]
        d.text((bx0 + 0.9 * SS, y), row, fill=LABEL, font=font)
        d.text((bx1 - 2.0 * SS, y), row, fill=LABEL, font=font)
    for name, sign in (("top_blue", "-"), ("top_red", "+"), ("bottom_red", "+"), ("bottom_blue", "-")):
        y = _px(0, g.line_y(name) - 0.9)[1]
        d.text((bx0 + 0.6 * SS, y), sign, fill=RED_LINE if sign == "+" else BLUE_LINE, font=font)


def _draw_battery(d: ImageDraw.ImageDraw) -> None:
    x0, y0 = _px(-37, 28)
    x1, y1 = _px(-15, 62)
    d.rounded_rectangle((x0, y0, x1, y1), radius=1.5 * SS, fill=(34, 34, 36))
    for i in range(2):
        cx0, cy0 = _px(-35 + i * 10, 31)
        cx1, cy1 = _px(-27 + i * 10, 59)
        d.rounded_rectangle((cx0, cy0, cx1, cy1), radius=3 * SS, fill=(30, 110, 60))
        d.rectangle((cx0, cy0, cx1, cy0 + 3 * SS), fill=(170, 170, 175))


def _draw_lead(d: ImageDraw.ImageDraw, lead: Lead) -> None:
    colour = (200, 30, 30) if lead.colour == "red" else (28, 28, 30)
    start = _px(-15, 40 if lead.colour == "red" else 46)
    mid = _px(10, 30 if lead.colour == "red" else 34)
    end = _hole_px(lead.to)
    _line(d, start, mid, 1.2, colour)
    _line(d, mid, end, 1.2, colour)
    _pin(d, end)


def _draw_resistor(d: ImageDraw.ImageDraw, res: Resistor) -> None:
    a, b = _hole_px(res.a), _hole_px(res.b)
    _line(d, a, b, 0.5, (165, 165, 170))
    _pin(d, a)
    _pin(d, b)
    angle = math.atan2(b[1] - a[1], b[0] - a[0])
    cx, cy = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
    d.polygon(_rot_rect(cx, cy, 6.4 * SS, 2.4 * SS, angle), fill=(212, 184, 140), outline=(140, 110, 70))
    for offset, colour in ((-2.0, (120, 66, 22)), (-1.0, (22, 22, 22)), (0.0, (120, 66, 22)), (1.9, (196, 158, 40))):
        bx = cx + offset * SS * math.cos(angle)
        by = cy + offset * SS * math.sin(angle)
        d.polygon(_rot_rect(bx, by, 0.55 * SS, 2.4 * SS, angle), fill=colour)


def _draw_led(d: ImageDraw.ImageDraw, led: Led) -> None:
    a, k = _hole_px(led.anode), _hole_px(led.cathode)
    _pin(d, a)
    _pin(d, k)
    cx, cy = (a[0] + k[0]) / 2, (a[1] + k[1]) / 2
    r = 2.5 * SS
    body = (215, 30, 30) if led.lit else (176, 18, 22)
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=body, outline=(110, 0, 6), width=int(0.25 * SS))
    # Flat rim edge on the cathode side: a chord cut drawn as a dark straight edge.
    ang = math.atan2(k[1] - a[1], k[0] - a[0])
    fx, fy = cx + 2.0 * SS * math.cos(ang), cy + 2.0 * SS * math.sin(ang)
    px, py = -math.sin(ang), math.cos(ang)
    half = 1.45 * SS
    d.polygon([(fx + px * half, fy + py * half), (fx - px * half, fy - py * half),
               (cx + 2.6 * SS * math.cos(ang) - px * half, cy + 2.6 * SS * math.sin(ang) - py * half),
               (cx + 2.6 * SS * math.cos(ang) + px * half, cy + 2.6 * SS * math.sin(ang) + py * half)], fill=BOARD)
    d.line([(fx + px * half, fy + py * half), (fx - px * half, fy - py * half)], fill=(90, 0, 4), width=int(0.3 * SS))
    hr = 0.8 * SS
    d.ellipse((cx - 1.2 * SS - hr, cy - 1.2 * SS - hr, cx - 1.2 * SS + hr, cy - 1.2 * SS + hr), fill=(246, 206, 206))  # specular highlight: bright but barely saturated


def _draw_button(d: ImageDraw.ImageDraw, btn: Button) -> None:
    pts = [_hole_px(h) for h in btn.legs]
    cx = sum(p[0] for p in pts) / 4
    cy = sum(p[1] for p in pts) / 4
    for p in pts:
        if btn.rotated:
            d.rectangle((p[0] - 0.3 * SS, p[1] - 0.9 * SS, p[0] + 0.3 * SS, p[1] + 0.9 * SS), fill=(172, 172, 178))
        else:
            d.rectangle((p[0] - 0.9 * SS, p[1] - 0.3 * SS, p[0] + 0.9 * SS, p[1] + 0.3 * SS), fill=(172, 172, 178))
    h = 3.0 * SS
    d.rounded_rectangle((cx - h, cy - h, cx + h, cy + h), radius=0.5 * SS, fill=(38, 38, 42), outline=(18, 18, 20),
                        width=int(0.2 * SS))
    r = 1.75 * SS
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(70, 70, 76), outline=(28, 28, 30), width=int(0.15 * SS))
    if btn.rotated:  # moulded orientation notch shows the 90° turn
        d.line((cx - h + 0.6 * SS, cy - 2.2 * SS, cx - h + 0.6 * SS, cy + 2.2 * SS), fill=(96, 96, 104), width=int(0.3 * SS))
    else:
        d.line((cx - 2.2 * SS, cy - h + 0.6 * SS, cx + 2.2 * SS, cy - h + 0.6 * SS), fill=(96, 96, 104), width=int(0.3 * SS))


def _draw_jumper(d: ImageDraw.ImageDraw, j: Jumper) -> None:
    colour = (28, 28, 30) if j.colour == "black" else (200, 30, 30)
    a, b = _hole_px(j.a), _hole_px(j.b)
    _line(d, a, b, 1.1, colour)
    _pin(d, a)
    _pin(d, b)
    d.line([a, b], fill=(80, 80, 84), width=int(0.2 * SS))


def _draw_finger(d: ImageDraw.ImageDraw, f: Finger) -> None:
    x, y = _hole_px(f.over)
    w = 4.6 * SS
    d.rounded_rectangle((x - w, y - 1.0 * SS, x + w, _px(0, 128)[1]), radius=w, fill=SKIN, outline=SKIN_EDGE,
                        width=int(0.3 * SS))
    d.ellipse((x - 2.8 * SS, y - 0.2 * SS, x + 2.8 * SS, y + 3.4 * SS), fill=(232, 196, 172))


def _draw_hand(d: ImageDraw.ImageDraw) -> None:
    cx, cy = _px(62, 58)
    d.ellipse((cx - 22 * SS, cy - 10 * SS, cx + 22 * SS, cy + 40 * SS), fill=SKIN, outline=SKIN_EDGE, width=int(0.4 * SS))
    for i, (dx, length) in enumerate(((-15, 20), (-6, 25), (3, 26), (12, 22))):
        x = cx + dx * SS
        top = cy - (length - 4 * (i == 0)) * SS
        d.rounded_rectangle((x - 3.6 * SS, top, x + 3.6 * SS, cy + 6 * SS), radius=3.6 * SS, fill=SKIN,
                            outline=SKIN_EDGE, width=int(0.3 * SS))


def _cover_markers(d: ImageDraw.ImageDraw) -> None:
    # A notebook lying over the right-hand side of the mat hides markers 1 and 2.
    x0, y0 = _px(112, -38)
    x1, y1 = _px(158, 128)
    d.rectangle((x0, y0, x1, y1), fill=(226, 224, 216), outline=(160, 158, 150), width=int(0.4 * SS))
    for k in range(12):
        y = _px(0, -30 + k * 12)[1]
        d.line((x0 + 2 * SS, y, x1 - 2 * SS, y), fill=(150, 170, 210), width=int(0.25 * SS))


def _markers(img: Image.Image) -> None:
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    side = int(round(g.MARKER_MM * SS))
    offsets = [(-g.MARKER_MM, -g.MARKER_MM), (g.MAT_W_MM, -g.MARKER_MM), (g.MAT_W_MM, g.MAT_H_MM), (-g.MARKER_MM, g.MAT_H_MM)]
    for marker_id, (dx, dy) in zip(g.MARKER_IDS, offsets, strict=True):
        tile = cv2.aruco.generateImageMarker(dictionary, marker_id, side)
        tile_rgb = np.stack([np.where(tile > 127, PAPER[i], 20) for i in range(3)], axis=-1).astype(np.uint8)
        x, y = _px(dx, dy)
        img.paste(Image.fromarray(tile_rgb), (int(round(x)), int(round(y))))


def render_mat_space(scene: Scene) -> np.ndarray:
    """Render the scene in mat space (OUT_SCALE px/mm), RGB, with anti-aliasing by supersampling."""
    size = (int(W_MM * SS), int(H_MM * SS))
    img = Image.new("RGB", size, DESK)
    d = ImageDraw.Draw(img)
    px0, py0 = _px(-38, -38)
    px1, py1 = _px(158, 128)
    d.rectangle((px0, py0, px1, py1), fill=PAPER)
    _markers(img)
    _draw_board(d)
    _draw_battery(d)
    order = (Lead, Resistor, Led, Button, Jumper, Finger)
    for kind in order:
        for part in scene.parts:
            if not isinstance(part, kind):
                continue
            {Lead: _draw_lead, Resistor: _draw_resistor, Led: _draw_led, Button: _draw_button, Jumper: _draw_jumper,
             Finger: _draw_finger}[kind](d, part)  # type: ignore[operator]
    if scene.cover_markers:
        _cover_markers(d)
    if scene.hand:
        _draw_hand(d)
    out = img.resize((int(W_MM * OUT_SCALE), int(H_MM * OUT_SCALE)), Image.LANCZOS)
    arr = np.asarray(out).astype(np.float32)
    if scene.shadow_over is not None:
        x, y = g.hole(*scene.shadow_over)
        yy, xx = np.mgrid[0:arr.shape[0], 0:arr.shape[1]]
        cx, cy = (x - X0) * OUT_SCALE, (y - Y0) * OUT_SCALE
        dist = ((xx - cx) / (4.5 * OUT_SCALE)) ** 2 + ((yy - cy) / (3.5 * OUT_SCALE)) ** 2
        arr *= (1.0 - 0.6 * np.exp(-dist))[..., None]
    lit = [p for p in scene.parts if isinstance(p, Led) and p.lit]
    for led in lit:
        a, k = g.hole(*led.anode), g.hole(*led.cathode)
        cx, cy = ((a[0] + k[0]) / 2 - X0) * OUT_SCALE, ((a[1] + k[1]) / 2 - Y0) * OUT_SCALE
        yy, xx = np.mgrid[0:arr.shape[0], 0:arr.shape[1]]
        r2 = ((xx - cx) ** 2 + (yy - cy) ** 2) / (OUT_SCALE ** 2)
        glow = np.exp(-r2 / (2 * 3.2 ** 2))
        core = np.exp(-r2 / (2 * 0.9 ** 2))
        arr[..., 0] += 140 * glow + 120 * core
        arr[..., 1] += 25 * glow + 150 * core
        arr[..., 2] += 20 * glow + 140 * core
    return np.clip(arr, 0, 255).astype(np.uint8)


def frame_transform() -> np.ndarray:
    """Homography from mat-space pixels to the 1920×1080 synthetic camera frame (mild perspective + tilt)."""
    w, h = W_MM * OUT_SCALE, H_MM * OUT_SCALE
    k = 1010.0 / h
    fw, fh = w * k, h * k
    cx, cy = FRAME_SIZE[0] / 2 + 20, FRAME_SIZE[1] / 2
    shrink = 0.035 * fw
    dst = np.array([[cx - fw / 2 + shrink, cy - fh / 2], [cx + fw / 2 - shrink, cy - fh / 2 + 8],
                    [cx + fw / 2, cy + fh / 2], [cx - fw / 2, cy + fh / 2 - 6]], dtype=np.float32)
    src = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
    return cv2.getPerspectiveTransform(src, dst)


def inner_quad_in_frame() -> np.ndarray:
    """Ground-truth frame coordinates of the mat's inner rectangle corners (TL, TR, BR, BL)."""
    pts = np.array([[[(0 - X0) * OUT_SCALE, (0 - Y0) * OUT_SCALE]],
                    [[(g.MAT_W_MM - X0) * OUT_SCALE, (0 - Y0) * OUT_SCALE]],
                    [[(g.MAT_W_MM - X0) * OUT_SCALE, (g.MAT_H_MM - Y0) * OUT_SCALE]],
                    [[(0 - X0) * OUT_SCALE, (g.MAT_H_MM - Y0) * OUT_SCALE]]], dtype=np.float32)
    return cv2.perspectiveTransform(pts, frame_transform()).reshape(4, 2)


def _to_frame(mat_rgb: np.ndarray) -> np.ndarray:
    bgr = cv2.cvtColor(mat_rgb, cv2.COLOR_RGB2BGR)
    frame = cv2.warpPerspective(bgr, frame_transform(), FRAME_SIZE, flags=cv2.INTER_LINEAR,
                                borderMode=cv2.BORDER_CONSTANT, borderValue=(DESK[2], DESK[1], DESK[0]))
    # Gentle lamp falloff so the frame does not look perfectly flat.
    yy, xx = np.mgrid[0:FRAME_SIZE[1], 0:FRAME_SIZE[0]].astype(np.float32)
    falloff = 1.04 - 0.12 * (((xx - 700) / FRAME_SIZE[0]) ** 2 + ((yy - 380) / FRAME_SIZE[1]) ** 2)
    return np.clip(frame.astype(np.float32) * falloff[..., None], 0, 255).astype(np.uint8)


def _apply_quality(frame: np.ndarray, label: str) -> np.ndarray:
    if label == "_dark":
        return (frame.astype(np.float32) * 0.28).astype(np.uint8)
    if label == "_blur":
        return cv2.GaussianBlur(frame, (0, 0), sigmaX=4.0)
    if label == "_glare":
        quad = inner_quad_in_frame()
        cx, cy = quad.mean(axis=0)
        out = frame.astype(np.float32)
        yy, xx = np.mgrid[0:frame.shape[0], 0:frame.shape[1]].astype(np.float32)
        dist = ((xx - cx + 40) / 190) ** 2 + ((yy - cy + 30) / 120) ** 2
        out += 255 * np.clip(1.6 - dist, 0, 1)[..., None]
        return np.clip(out, 0, 255).astype(np.uint8)
    return frame


def render_scene(step: str, label: str) -> np.ndarray:
    """Render one synthetic camera frame (BGR, 1920×1080)."""
    scene = build_scene(step, label)
    return _apply_quality(_to_frame(render_mat_space(scene)), label)


def render_all(out_dir: Path, steps: Iterable[str] | None = None, labels: Iterable[str] | None = None) -> list[Path]:
    """Render every (step, label) scene to ``out_dir/<step>/<label>.png`` and update the synthetic manifest."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    wanted = set(labels) if labels else None
    for step in steps or STEPS:
        for label in scene_labels(step):
            if wanted and label not in wanted:
                continue
            path = out_dir / step / f"{label}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(path), render_scene(step, label), [cv2.IMWRITE_PNG_COMPRESSION, 6])
            written.append(path)
    manifest_path = out_dir / SYNTHETIC_MANIFEST
    existing: set[str] = set()
    if manifest_path.exists():
        existing = set(json.loads(manifest_path.read_text(encoding="utf-8")).get("files", []))
    existing |= {p.relative_to(out_dir).as_posix() for p in written}
    manifest_path.write_text(json.dumps({"note": "Synthetic placeholders: never use for accuracy claims.",
                                         "files": sorted(existing)}, indent=2), encoding="utf-8")
    return written
