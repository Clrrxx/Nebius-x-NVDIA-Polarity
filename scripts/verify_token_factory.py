#!/usr/bin/env python3
"""Standalone Phase 0 verifier: thin wrapper around polarity.verify.run_verify.

Needs only: openai, python-dotenv, pillow, numpy, rich (and opencv-contrib-python for the optional
video test). Usage:  python scripts/verify_token_factory.py [--record] [--skip-video] [--json]
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from polarity.verify.run_verify import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
