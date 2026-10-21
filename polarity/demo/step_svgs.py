"""Step illustrations (``static/img/steps/s1.svg`` … ``s6.svg``) drawn from the same breadboard geometry as the
synthetic renderer: earlier steps are faded, the current step's part is highlighted with a teal halo and a short
label. Regenerate with ``python tools/make_step_svgs.py``.
"""

from __future__ import annotations

import math
from pathlib import Path

from polarity.demo import geometry as g
from polarity.demo.synthetic_board import CORRECT, STEPS, Button, Finger, Jumper, Lead, Led, Resistor

TEAL = "#2DD4BF"
RED = "#EF4444"
BLUE = "#3B82F6"
BOARD = "#ECE8DE"
BOARD_EDGE = "#B9B3A6"
CHANNEL = "#DCD6C9"
HOLE = "#6B7280"
LABEL = "#8B8579"

ANNOTATIONS: dict[str, list[tuple[str, tuple[str, float], tuple[float, float]]]] = {
    "s1": [("red → + rail", ("T+", 1), (6, 9)), ("black → − rail", ("T-", 1), (6, -5))],
    "s2": [("+ rail → strip 10", ("b", 10), (9, 3))],
    "s3": [("long leg (+) in strip 10", ("d", 10), (-24, 9)), ("flat edge / short leg", ("d", 11), (5, 7))],
    "s4": [("across the channel", ("f", 12), (6, 7))],
    "s5": [("black jumper → − rail", ("a", 13), (6, 4))],
    "s6": [("switch ON, hold button", ("f", 12), (7, 8))],
}


def _f(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


def _hole(h: tuple[str, float]) -> tuple[float, float]:
    return g.hole(h[0], h[1])


def _board() -> list[str]:
    out = [f'<rect x="{_f(g.BOARD_X_MM)}" y="{_f(g.BOARD_Y_MM)}" width="{_f(g.BOARD_W_MM)}" height="{_f(g.BOARD_H_MM)}" '
           f'rx="2" fill="{BOARD}" stroke="{BOARD_EDGE}" stroke-width="0.5"/>']
    cy = g.channel_y()
    out.append(f'<rect x="{_f(g.BOARD_X_MM + 0.8)}" y="{_f(cy - 1.2)}" width="{_f(g.BOARD_W_MM - 1.6)}" height="2.4" fill="{CHANNEL}"/>')
    for name, colour in (("top_blue", BLUE), ("top_red", RED), ("bottom_red", RED), ("bottom_blue", BLUE)):
        y = g.line_y(name)
        out.append(f'<line x1="{_f(g.BOARD_X_MM + 2)}" y1="{_f(y)}" x2="{_f(g.BOARD_X_MM + g.BOARD_W_MM - 2)}" '
                   f'y2="{_f(y)}" stroke="{colour}" stroke-width="0.5"/>')
    holes = "".join(f'<rect x="{_f(x - 0.45)}" y="{_f(y - 0.45)}" width="0.9" height="0.9"/>'
                    for x, y in (g.hole(r, c) for r, c in g.all_holes()))
    out.append(f'<g fill="{HOLE}">{holes}</g>')
    labels = []
    for col in (1, 5, 10, 15, 20, 25, 30):
        x = g.col_x(col)
        labels.append(f'<text x="{_f(x)}" y="{_f(g.row_y("a") - 1.6)}" text-anchor="middle">{col}</text>')
        labels.append(f'<text x="{_f(x)}" y="{_f(g.row_y("j") + 2.6)}" text-anchor="middle">{col}</text>')
    for row in g.STRIP_ROWS:
        labels.append(f'<text x="{_f(g.BOARD_X_MM + 1.6)}" y="{_f(g.row_y(row) + 0.6)}" text-anchor="middle">{row}</text>')
    for name, sign, colour in (("top_blue", "−", BLUE), ("top_red", "+", RED), ("bottom_red", "+", RED),
                               ("bottom_blue", "−", BLUE)):
        labels.append(f'<text x="{_f(g.BOARD_X_MM - 1.8)}" y="{_f(g.line_y(name) + 0.7)}" text-anchor="middle" '
                      f'fill="{colour}" font-size="2.4" font-weight="700">{sign}</text>')
    out.append(f'<g fill="{LABEL}" font-size="1.5" font-family="system-ui, -apple-system, Segoe UI, sans-serif">'
               + "".join(labels) + "</g>")
    return out


def _part(p: object, highlight: bool, lit: bool = False) -> list[str]:
    halo = f' stroke="{TEAL}" stroke-opacity="0.45" stroke-linecap="round"' if highlight else ""
    out: list[str] = []
    if isinstance(p, Lead):
        colour = "#DC2626" if p.colour == "red" else "#1F2937"
        x, y = _hole(p.to)
        sx, sy = g.BOARD_X_MM - 9, y + (5 if p.colour == "red" else 2)
        if highlight:
            out.append(f'<path d="M{_f(sx)} {_f(sy)} L{_f(x)} {_f(y)}" fill="none" stroke-width="3.4"{halo}/>')
        out.append(f'<path d="M{_f(sx)} {_f(sy)} L{_f(x)} {_f(y)}" fill="none" stroke="{colour}" stroke-width="1.2" stroke-linecap="round"/>')
        out.append(f'<rect x="{_f(x - 0.55)}" y="{_f(y - 0.55)}" width="1.1" height="1.1" fill="#9CA3AF"/>')
    elif isinstance(p, Resistor):
        (ax, ay), (bx, by) = _hole(p.a), _hole(p.b)
        ang = math.degrees(math.atan2(by - ay, bx - ax))
        cx, cy = (ax + bx) / 2, (ay + by) / 2
        if highlight:
            out.append(f'<line x1="{_f(ax)}" y1="{_f(ay)}" x2="{_f(bx)}" y2="{_f(by)}" stroke-width="4.2"{halo}/>')
        out.append(f'<line x1="{_f(ax)}" y1="{_f(ay)}" x2="{_f(bx)}" y2="{_f(by)}" stroke="#9CA3AF" stroke-width="0.5"/>')
        bands = "".join(f'<rect x="{_f(o)}" y="-1.2" width="0.55" height="2.4" fill="{c}"/>'
                        for o, c in ((-2.3, "#7C4A1E"), (-1.3, "#111827"), (-0.3, "#7C4A1E"), (1.6, "#C9A227")))
        out.append(f'<g transform="translate({_f(cx)} {_f(cy)}) rotate({_f(ang)})"><rect x="-3.2" y="-1.2" width="6.4" '
                   f'height="2.4" rx="1" fill="#D6B98A" stroke="#8C6B3F" stroke-width="0.2"/>{bands}</g>')
    elif isinstance(p, Led):
        (ax, ay), (kx, ky) = _hole(p.anode), _hole(p.cathode)
        cx, cy = (ax + kx) / 2, (ay + ky) / 2
        ang = math.degrees(math.atan2(ky - ay, kx - ax))
        if lit:
            out.append(f'<circle cx="{_f(cx)}" cy="{_f(cy)}" r="7" fill="url(#glow)"/>')
        if highlight:
            out.append(f'<circle cx="{_f(cx)}" cy="{_f(cy)}" r="4" fill="none" stroke-width="1.8"{halo}/>')
        fill = "#F87171" if lit else "#DC2626"
        # Dome with a flat edge on the cathode side (chord at x = 2.0 in the LED's own frame).
        out.append(f'<g transform="translate({_f(cx)} {_f(cy)}) rotate({_f(ang)})">'
                   f'<path d="M2 -1.5 A2.5 2.5 0 1 0 2 1.5 Z" fill="{fill}" stroke="#7F1D1D" stroke-width="0.25"/>'
                   f'<circle cx="-1" cy="-1" r="0.6" fill="#FECACA"/></g>')
    elif isinstance(p, Button):
        pts = [_hole(h) for h in p.legs]
        cx, cy = sum(x for x, _ in pts) / 4, sum(y for _, y in pts) / 4
        if highlight:
            out.append(f'<rect x="{_f(cx - 4.4)}" y="{_f(cy - 4.4)}" width="8.8" height="8.8" rx="1.5" fill="none" stroke-width="1.6"{halo}/>')
        out += [f'<rect x="{_f(x - 0.9)}" y="{_f(y - 0.3)}" width="1.8" height="0.6" fill="#9CA3AF"/>' for x, y in pts]
        out.append(f'<rect x="{_f(cx - 3)}" y="{_f(cy - 3)}" width="6" height="6" rx="0.5" fill="#1F2937"/>'
                   f'<circle cx="{_f(cx)}" cy="{_f(cy)}" r="1.75" fill="#4B5563"/>')
    elif isinstance(p, Jumper):
        (ax, ay), (bx, by) = _hole(p.a), _hole(p.b)
        if highlight:
            out.append(f'<line x1="{_f(ax)}" y1="{_f(ay)}" x2="{_f(bx)}" y2="{_f(by)}" stroke-width="3.4"{halo}/>')
        out.append(f'<line x1="{_f(ax)}" y1="{_f(ay)}" x2="{_f(bx)}" y2="{_f(by)}" stroke="#1F2937" stroke-width="1.1" stroke-linecap="round"/>')
    elif isinstance(p, Finger):
        x, y = _hole(p.over)
        out.append(f'<rect x="{_f(x - 4.2)}" y="{_f(y - 0.5)}" width="8.4" height="{_f(g.BOARD_Y_MM + g.BOARD_H_MM + 6 - y)}" '
                   f'rx="4.2" fill="#E0B596" fill-opacity="0.85" stroke="#B9876A" stroke-width="0.3"/>')
    return out


def render_step_svg(step: str) -> str:
    """SVG text for one step (viewBox in millimetres)."""
    pad = 9.0
    x0, y0 = g.BOARD_X_MM - pad - 4, g.BOARD_Y_MM - pad
    w, h = g.BOARD_W_MM + 2 * pad + 4, g.BOARD_H_MM + 2 * pad
    idx = STEPS.index(step)
    body = _board()
    lit = step == "s6"
    for prev in STEPS[:idx]:
        faded = [s for p in CORRECT[prev] if not isinstance(p, Finger) for s in _part(p, False, lit and isinstance(p, Led))]
        body.append('<g opacity="0.5">' + "".join(faded) + "</g>" if not lit else "".join(faded))
    for p in CORRECT[step]:
        body += _part(p, True)
    notes = []
    for text, hole, (dx, dy) in ANNOTATIONS.get(step, []):
        hx, hy = _hole(hole)
        tx, ty = hx + dx, hy + dy
        notes.append(f'<line x1="{_f(hx)}" y1="{_f(hy)}" x2="{_f(tx)}" y2="{_f(ty - 0.8)}" stroke="{TEAL}" stroke-width="0.35"/>'
                     f'<text x="{_f(tx)}" y="{_f(ty)}" fill="#0F766E" font-size="2.3" font-weight="600" '
                     f'paint-order="stroke" stroke="#FFFFFF" stroke-width="0.6">{text}</text>')
    title = {"s1": "Power rails", "s2": "Resistor", "s3": "LED", "s4": "Push button", "s5": "Ground wire",
             "s6": "Power test"}[step]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{_f(x0)} {_f(y0)} {_f(w)} {_f(h)}" role="img" '
            f'aria-label="Step illustration: {title}" '
            'font-family="system-ui, -apple-system, Segoe UI, Roboto, Helvetica Neue, Arial, sans-serif">'
            f'<title>Step {idx + 1}: {title}</title>'
            '<defs><radialGradient id="glow"><stop offset="0" stop-color="#FCA5A5" stop-opacity="0.95"/>'
            '<stop offset="0.45" stop-color="#EF4444" stop-opacity="0.45"/>'
            '<stop offset="1" stop-color="#EF4444" stop-opacity="0"/></radialGradient></defs>'
            + "".join(body) + "".join(notes) + "</svg>\n")


def write_all(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for step in STEPS:
        path = out_dir / f"{step}.svg"
        path.write_text(render_step_svg(step), encoding="utf-8")
        paths.append(path)
    return paths
