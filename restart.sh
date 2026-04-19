#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/home/erik-poppe/.openclaw/workspace/Treningsanalyse"
FRONTEND_DIR="$ROOT_DIR/frontend"
VENV_PY="$ROOT_DIR/.venv/bin/python"
BACKEND_APP="app.main:app"
BACKEND_PORT="8000"
FRONTEND_PORT="3000"
DB_URL="sqlite:////home/erik-poppe/.openclaw/workspace/Treningsanalyse/backend/data/treningsanalyse.db"
RUN_DIR="$ROOT_DIR/.run"
BACKEND_LOG="$RUN_DIR/backend.log"
FRONTEND_LOG="$RUN_DIR/frontend.log"

mkdir -p "$RUN_DIR"

echo "Stopper gamle prosesser for din bruker..."
pkill -u "$USER" -f "uvicorn $BACKEND_APP" 2>/dev/null || true
pkill -u "$USER" -f "next dev" 2>/dev/null || true
pkill -u "$USER" -f "npm run dev -- --hostname 0.0.0.0 --port $FRONTEND_PORT" 2>/dev/null || true

sleep 1

echo "Starter backend på port $BACKEND_PORT..."
nohup env DATABASE_URL="$DB_URL" PYTHONPATH=backend "$VENV_PY" -m uvicorn "$BACKEND_APP" --host 0.0.0.0 --port "$BACKEND_PORT" \
  >"$BACKEND_LOG" 2>&1 &
BACKEND_PID=$!

echo "Starter frontend på port $FRONTEND_PORT..."
nohup bash -lc "cd \"$FRONTEND_DIR\" && npm run dev -- --hostname 0.0.0.0 --port $FRONTEND_PORT" \
  >"$FRONTEND_LOG" 2>&1 &
FRONTEND_PID=$!

echo "Venter på oppstart..."
sleep 4

echo ""
echo "Prosesser startet:"
echo "- Backend PID:  $BACKEND_PID"
echo "- Frontend PID: $FRONTEND_PID"
echo ""
echo "URL-er:"
echo "- Frontend: http://localhost:$FRONTEND_PORT"
echo "- Backend:  http://localhost:$BACKEND_PORT"
echo ""
echo "Logger:"
echo "- $BACKEND_LOG"
echo "- $FRONTEND_LOG"
echo ""
echo "Tips: bruk 'tail -f \"$BACKEND_LOG\"' eller 'tail -f \"$FRONTEND_LOG\"' ved behov."
