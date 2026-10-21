"""Regenerate the Lab 1 step illustrations in polarity/web/static/img/steps/ from the breadboard geometry."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from polarity.demo.step_svgs import write_all  # noqa: E402

if __name__ == "__main__":
    for path in write_all(ROOT / "polarity" / "web" / "static" / "img" / "steps"):
        print(path.relative_to(ROOT))
