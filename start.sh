#!/usr/bin/env bash
# Start backend and frontend dev servers for the floorplan workspace MVP.

set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "Starting backend on :8000..."
cd "$ROOT/backend"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt -q
else
  source .venv/bin/activate
fi
uvicorn app.main:app --reload --port 8000 &
BACKEND_PID=$!

echo "Starting frontend on :3000..."
cd "$ROOT/frontend"
if [ ! -d node_modules ]; then
  npm install
fi
npm run dev &
FRONTEND_PID=$!

echo ""
echo "Floorplan Workspace MVP running:"
echo "  Frontend: http://localhost:3000"
echo "  Backend:  http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop both servers."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
wait
