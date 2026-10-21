#!/usr/bin/env bash
# Phase 0: verify Nebius Token Factory + Nemotron capabilities (macOS / Linux).
# Usage: scripts/verify_mac.sh [--record] [--skip-video] [--json]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONIOENCODING=utf-8
if [ ! -x ".venv/bin/python" ]; then
  echo "No .venv found. Run scripts/setup_mac.sh first."
  exit 1
fi
exec ".venv/bin/python" -m polarity verify "$@"
