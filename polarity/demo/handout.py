"""Sample lab handout PDF (``labs/samples/lab1_handout.pdf``) generated from ``labs/lab1.yaml`` with Pillow, so the
lab compiler can be demoed on a realistic printed sheet. Regenerate with ``python tools/make_sample_handout.py``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from polarity.demo import geometry as g
from polarity.demo.synthetic_board import OUT_SCALE, X0, Y0, build_scene, render_mat_space
from polarity.imaging import get_font
from polarity.models.lab import LabDefinition

DPI = 150
PAGE = (int(8.27 * DPI), int(11.69 * DPI))  # A4 portrait
MARGIN = 110
INK = (25, 25, 25)
MUTED = (95, 95, 95)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: object, width: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= width:  # type: ignore[arg-type]
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def _board_figure(step_id: str, width: int) -> Image.Image:
    """Top-down picture of the board after this step is done correctly (from the synthetic renderer)."""
    rgb = render_mat_space(build_scene(step_id, "correct"))
    x0 = int((g.BOARD_X_MM - 4 - X0) * OUT_SCALE)
    y0 = int((g.BOARD_Y_MM - 3 - Y0) * OUT_SCALE)
    x1 = int((g.BOARD_X_MM + g.BOARD_W_MM + 3 - X0) * OUT_SCALE)
    y1 = int((g.BOARD_Y_MM + g.BOARD_H_MM + 3 - Y0) * OUT_SCALE)
    crop = Image.fromarray(np.ascontiguousarray(rgb[y0:y1, x0:x1]))
    return crop.resize((width, int(crop.height * width / crop.width)), Image.LANCZOS)


def render_handout(lab: LabDefinition) -> list[Image.Image]:
    pages: list[Image.Image] = []
    title_f, h_f, body_f, small_f = get_font(46, bold=True), get_font(30, bold=True), get_font(24), get_font(20)
    text_w = PAGE[0] - 2 * MARGIN

    def new_page() -> tuple[Image.Image, ImageDraw.ImageDraw, int]:
        img = Image.new("RGB", PAGE, (255, 255, 255))
        d = ImageDraw.Draw(img)
        d.text((MARGIN, PAGE[1] - 70), f"{lab.title} · page {len(pages) + 1}", fill=MUTED, font=small_f)
        return img, d, MARGIN

    img, d, y = new_page()
    d.text((MARGIN, y), "Introductory Electronics · Lab handout", fill=MUTED, font=small_f)
    y += 40
    d.text((MARGIN, y), lab.title, fill=INK, font=title_f)
    y += 70
    for line in _wrap(d, lab.summary, body_f, text_w):
        d.text((MARGIN, y), line, fill=INK, font=body_f)
        y += 34
    y += 16
    d.text((MARGIN, y), "You will need", fill=INK, font=h_f)
    y += 46
    for item in lab.kit:
        for i, line in enumerate(_wrap(d, item, body_f, text_w - 30)):
            d.text((MARGIN + (0 if i else 0), y), ("•  " if i == 0 else "    ") + line, fill=INK, font=body_f)
            y += 32
    y += 14
    box_top = y
    safety = [line for note in lab.safety_notes for line in _wrap(d, note, body_f, text_w - 40)]
    d.rectangle((MARGIN, box_top, PAGE[0] - MARGIN, box_top + 56 + 32 * len(safety)), outline=(200, 120, 0), width=3)
    d.text((MARGIN + 20, box_top + 12), "SAFETY", fill=(160, 90, 0), font=h_f)
    y = box_top + 56
    for line in safety:
        d.text((MARGIN + 20, y), line, fill=INK, font=body_f)
        y += 32
    y += 40
    fig_w = 380
    for n, step in enumerate(lab.steps, start=1):
        lines = _wrap(d, step.instruction, body_f, text_w - fig_w - 30)
        block_h = max(70 + 32 * len(lines), int(fig_w * 0.72) + 20)
        if y + block_h > PAGE[1] - 110:
            pages.append(img)
            img, d, y = new_page()
        d.text((MARGIN, y), f"Step {n}: {step.title}", fill=INK, font=h_f)
        ty = y + 46
        for line in lines:
            d.text((MARGIN, ty), line, fill=INK, font=body_f)
            ty += 32
        fig = _board_figure(step.id, fig_w)
        img.paste(fig, (PAGE[0] - MARGIN - fig_w, y + 4))
        d.text((PAGE[0] - MARGIN - fig_w, y + 8 + fig.height), f"Figure {n}: board after step {n}", fill=MUTED, font=small_f)
        y += block_h + 14
    if y > PAGE[1] - 150:
        pages.append(img)
        img, d, y = new_page()
    d.text((MARGIN, y), "Checkpoint: show your TA the lit LED before you pack up.", fill=INK, font=h_f)
    pages.append(img)
    return pages


def write_handout(lab: LabDefinition, path: Path) -> Path:
    pages = render_handout(lab)
    path.parent.mkdir(parents=True, exist_ok=True)
    pages[0].save(path, "PDF", resolution=float(DPI), save_all=True, append_images=pages[1:])
    return path
