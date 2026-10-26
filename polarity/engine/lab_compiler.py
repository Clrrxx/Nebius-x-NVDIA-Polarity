"""Lab-sheet compiler (BUILD_PROMPT.md 13.1, P1): any lab handout → a verifiable step definition.

Pages are rendered with pypdfium2 at 150 dpi (photos are accepted directly). The perception model (Super VL on our account) reads each page
(document understanding), then Nemotron Super assembles a ``LabDefinition``, which is validated and saved as an
AI-drafted lab that a TA must review in the editor before publishing. Capped at 10 pages, with a cost estimate
shown before anything runs.
"""

from __future__ import annotations

import io
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image
from pydantic import ValidationError

from polarity.imaging import pil_to_bytes, resize_long_side
from polarity.llm import prompts
from polarity.llm.jsonio import format_validation_errors
from polarity.llm.payloads import image_part, text_part
from polarity.llm.pricing import estimate_cost
from polarity.models.lab import LabDefinition
from polarity.models.verdict import PageExtract
from polarity.storage.db import new_id

log = logging.getLogger(__name__)

MAX_PAGES = 10
RENDER_DPI = 150
# Rough token budget per call, used only for the pre-run estimate shown to the TA.
EST_PAGE_TOKENS = (1800, 500)      # (prompt incl. image, completion) per page read
EST_ASSEMBLE_TOKENS = (2500, 3500)
IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


class CompileError(Exception):
    pass


@dataclass
class Upload:
    id: str
    folder: Path
    pages: list[Path]


def render_pages(name: str, data: bytes, out_dir: Path, start_index: int = 0) -> list[Path]:
    """Save each page of a PDF (or one image) as PNG; returns the page image paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(name).suffix.lower()
    paths: list[Path] = []
    if suffix == ".pdf" or data[:4] == b"%PDF":
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(data)
        try:
            for i in range(len(pdf)):
                if start_index + i >= MAX_PAGES:
                    break
                img = pdf[i].render(scale=RENDER_DPI / 72).to_pil().convert("RGB")
                path = out_dir / f"page_{start_index + i + 1:02d}.png"
                img.save(path, "PNG")
                paths.append(path)
        finally:
            pdf.close()
    elif suffix in IMAGE_TYPES:
        try:
            img = Image.open(io.BytesIO(data)).convert("RGB")
        except OSError as exc:
            raise CompileError(f"{name} is not a readable image.") from exc
        path = out_dir / f"page_{start_index + 1:02d}.png"
        img.save(path, "PNG")
        paths.append(path)
    else:
        raise CompileError(f"{name}: upload a PDF or photos (PNG/JPG).")
    return paths


def create_upload(media_root: Path, files: list[tuple[str, bytes]]) -> Upload:
    upload_id = new_id()
    folder = media_root / "compile" / upload_id
    pages: list[Path] = []
    for name, data in files:
        if len(pages) >= MAX_PAGES:
            break
        pages += render_pages(name, data, folder, start_index=len(pages))
    if not pages:
        raise CompileError("No pages found in the upload.")
    return Upload(upload_id, folder, pages[:MAX_PAGES])


def load_upload(media_root: Path, upload_id: str) -> Upload:
    if not re.fullmatch(r"[0-9a-f]{32}", upload_id):
        raise CompileError("Unknown upload.")
    folder = media_root / "compile" / upload_id
    pages = sorted(folder.glob("page_*.png"))
    if not pages:
        raise CompileError("Unknown upload.")
    return Upload(upload_id, folder, pages)


def estimate(config: Any, n_pages: int) -> dict[str, Any]:
    """Token and cost estimate before running (cost is n/a until prices are in config/pricing.yaml)."""
    p_in, p_out = EST_PAGE_TOKENS[0] * n_pages, EST_PAGE_TOKENS[1] * n_pages
    a_in, a_out = EST_ASSEMBLE_TOKENS
    perception = config.model_for("perception")
    reasoning = config.model_for("reasoning")
    c1 = estimate_cost(perception.id if perception else None, p_in, p_out, config.prices)
    c2 = estimate_cost(reasoning.id if reasoning else None, a_in, a_out, config.prices)
    cost = None if c1 is None or c2 is None else round(c1 + c2, 4)
    return {"pages": n_pages, "calls": n_pages + 1, "tokens_estimate": p_in + p_out + a_in + a_out,
            "cost_estimate_usd": cost, "max_pages": MAX_PAGES}


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug[:40] or "lab"


def compile_upload(rt: Any, upload: Upload, progress: Any = None) -> dict[str, Any]:
    """Run page reading + assembly. Returns ``{"lab": dict|None, "errors": str|None, "pages": [...], "draft_id"}``."""
    extracts: list[dict[str, Any]] = []
    for i, page in enumerate(upload.pages):
        if progress:
            progress({"stage": "page", "page": i + 1, "total": len(upload.pages)})
        img = resize_long_side(Image.open(page).convert("RGB"), 1600)
        res = rt.router.call("perception", [
            {"role": "system", "content": prompts.LAB_COMPILER_PAGE_SYSTEM},
            {"role": "user", "content": [text_part(f"Page {i + 1} of {len(upload.pages)}."),
                                         image_part(pil_to_bytes(img, "JPEG", 88), "image/jpeg")]}],
            schema=PageExtract, max_tokens=1500, interactive=False)
        extracts.append({"page": i + 1, **res.parsed.model_dump()})  # type: ignore[union-attr]
    if progress:
        progress({"stage": "assemble", "page": len(upload.pages), "total": len(upload.pages)})
    res = rt.router.call("reasoning", [
        {"role": "system", "content": prompts._named(prompts.LAB_COMPILER_ASSEMBLE_SYSTEM)},
        {"role": "user", "content": json.dumps({"pages": extracts}, ensure_ascii=False)}],
        schema=LabDefinition, max_tokens=6000, interactive=False)
    lab: LabDefinition = res.parsed  # type: ignore[assignment]
    lab = lab.model_copy(update={"ai_drafted": True})
    if rt.labs.get(lab.id) is not None and not lab.id.startswith("lab_compiled"):
        lab = lab.model_copy(update={"id": f"{_slug(lab.id)}_draft"})
    rt.labs.save(lab, publish=False)
    if progress:
        progress({"stage": "done", "page": len(upload.pages), "total": len(upload.pages), "lab_id": lab.id})
    return {"lab": lab.model_dump(mode="json"), "errors": None, "pages": extracts, "lab_id": lab.id,
            "model_ids": sorted({res.model_id})}


def validate_lab(data: dict[str, Any]) -> tuple[LabDefinition | None, str | None]:
    try:
        return LabDefinition.model_validate(data), None
    except ValidationError as exc:
        return None, format_validation_errors(exc, limit=20)
