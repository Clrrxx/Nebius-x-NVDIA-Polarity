#!/usr/bin/env bash
# Start Polarity and open the browser (macOS / Linux). Extra arguments are passed to `polarity run`,
# e.g.  scripts/run_mac.sh --role hub   or   CAMERA_SOURCE=demo POLARITY_MOCK_MODELS=1 scripts/run_mac.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONIOENCODING=utf-8
if [ ! -x ".venv/bin/python" ]; then
  echo "No .venv found. Run scripts/setup_mac.sh first."
  exit 1
fi
exec ".venv/bin/python" -m polarity run --open-browser "$@"
