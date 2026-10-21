"""Regenerate labs/samples/lab1_handout.pdf (the lab-compiler demo input) from labs/lab1.yaml."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from polarity.demo.handout import write_handout  # noqa: E402
from polarity.models.lab import load_lab  # noqa: E402

if __name__ == "__main__":
    out = write_handout(load_lab(ROOT / "labs" / "lab1.yaml"), ROOT / "labs" / "samples" / "lab1_handout.pdf")
    print(out.relative_to(ROOT), f"{out.stat().st_size // 1024} KB")
