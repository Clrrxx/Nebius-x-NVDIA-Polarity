#!/usr/bin/env bash
# One-time setup for macOS (Apple Silicon or Intel) and Linux: Python venv, dependencies, .env, demo scenes, doctor.
# Usage: scripts/setup_mac.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONIOENCODING=utf-8

version_of() { "$1" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true; }

PY=""
for cand in python3.12 python3.11 python3; do
  if command -v "$cand" >/dev/null 2>&1; then
    v="$(version_of "$cand")"
    if [ "$v" = "3.12" ] || [ "$v" = "3.11" ]; then PY="$(command -v "$cand")"; break; fi
  fi
done
if [ -z "$PY" ]; then
  echo "Polarity needs Python 3.12 (3.11 also works; 3.13+ is not supported yet)."
  echo "  macOS:  brew install python@3.12      (or download from https://www.python.org/downloads/macos/)"
  echo "  Linux:  sudo apt install python3.12 python3.12-venv   (or your distribution's equivalent)"
  exit 1
fi
echo "Using $PY ($(version_of "$PY"))"

if [ -x ".venv/bin/python" ]; then
  have="$(version_of .venv/bin/python)"
  if [ "$have" != "3.12" ] && [ "$have" != "3.11" ]; then
    echo "Existing .venv uses Python $have; recreating it with $(version_of "$PY")."
    rm -rf .venv
  fi
fi
[ -x ".venv/bin/python" ] || "$PY" -m venv .venv

.venv/bin/python -m pip install -U pip wheel
.venv/bin/python -m pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m pip install -e .

if [ ! -f .env ]; then
  cp .env.example .env
  if grep -q '^NEBIUS_API_KEY=..*' .env.local 2>/dev/null; then
    echo "Created .env from .env.example. The key in .env.local is used (it overrides .env), so no need to edit .env."
  else
    echo "Created .env from .env.example. Paste your NEBIUS_API_KEY into it."
  fi
fi

echo "Rendering demo scenes (synthetic placeholders for demo mode)..."
.venv/bin/python -m polarity render-synthetic >/dev/null

.venv/bin/python -m polarity doctor
echo
echo "Next: scripts/verify_mac.sh (needs NEBIUS_API_KEY), then scripts/run_mac.sh"
