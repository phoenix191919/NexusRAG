#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  echo "Missing .venv — create with: python -m venv .venv" >&2
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate
export PYTHONPATH=backend
echo "API → http://127.0.0.1:8000  docs → /docs"
exec uvicorn app.main:app --reload --app-dir backend --host 127.0.0.1 --port 8000
