#!/usr/bin/env bash
# hp_web — launch the local dashboard.
#
# Builds the React frontend if dist/ is missing or stale, then runs the
# FastAPI server on 127.0.0.1:8765. Pass --dev to run Vite + uvicorn
# concurrently for hot-reload (frontend on :5173, API on :8765).
#
# Local-only by design: the backend never binds outside 127.0.0.1.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
WEB="$ROOT/web"
FRONT="$WEB/frontend"
DIST="$FRONT/dist"
VENV="$WEB/.venv"

# Load API keys for the wargame mode (which calls OpenRouter via
# hp_vision.py). Looks in two places, in order:
#   ~/.hammerstein.env   (user-global)
#   ./.env               (project-local, gitignored)
# Either may set OPENROUTER_API_KEY=... and any other env vars
# hp_vision.py needs. Both are optional — the dashboard tab works
# without any keys; only the wargame tab's "Issue orders" requires it.
for env_file in "$HOME/.hammerstein.env" "$ROOT/.env"; do
  if [ -f "$env_file" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$env_file"
    set +a
  fi
done

if [ ! -d "$VENV" ]; then
  echo "hp_web: creating venv at $VENV"
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install -q -r "$WEB/requirements.txt"
fi

mode="prod"
if [ "${1:-}" = "--dev" ]; then mode="dev"; fi

if [ "$mode" = "prod" ]; then
  needs_build=0
  if [ ! -d "$DIST" ]; then needs_build=1; fi
  if [ -d "$DIST" ] && [ -n "$(find "$FRONT/src" -newer "$DIST/index.html" 2>/dev/null | head -1)" ]; then
    needs_build=1
  fi
  if [ "$needs_build" = "1" ]; then
    echo "hp_web: building frontend"
    (cd "$FRONT" && npm install --silent && npm run build)
  fi
  echo "hp_web: serving on http://127.0.0.1:8765"
  exec "$VENV/bin/python" -m uvicorn web.backend.server:app --host 127.0.0.1 --port 8765
else
  echo "hp_web: dev mode — Vite on :5173 (open this), API on :8765"
  trap 'kill 0' EXIT INT TERM
  (cd "$FRONT" && npm install --silent && npm run dev) &
  "$VENV/bin/python" -m uvicorn web.backend.server:app --host 127.0.0.1 --port 8765 --reload &
  wait
fi
