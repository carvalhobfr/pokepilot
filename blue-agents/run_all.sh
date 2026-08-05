#!/bin/bash

set -u
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
PYTHON_BIN="$SCRIPT_DIR/../.venv/bin/python"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN="python3"
TRAINING_PID_FILE="$SCRIPT_DIR/tasks/training.pid"
export MPLCONFIGDIR="$SCRIPT_DIR/tasks/matplotlib"
mkdir -p "$SCRIPT_DIR/tasks" "$MPLCONFIGDIR"

MODE="real"
if [ "${1:-}" = "--demo" ]; then
  MODE="demo"
  shift
elif [ "${1:-}" = "--journeys" ]; then
  MODE="journeys"
  shift
fi

cleanup() {
  echo "\n🛑 Encerrando PokeAI 2026..."
  if [ -n "${WORKER_PID:-}" ]; then
    kill -CONT "$WORKER_PID" 2>/dev/null || true
    kill "$WORKER_PID" 2>/dev/null || true
  fi
  [ -n "${VIZ_PID:-}" ] && kill "$VIZ_PID" 2>/dev/null || true
  if [ -f "$TRAINING_PID_FILE" ] && [ "$(tr -d '[:space:]' < "$TRAINING_PID_FILE")" = "${WORKER_PID:-}" ]; then
    rm -f "$TRAINING_PID_FILE"
  fi
}
trap cleanup INT TERM EXIT

echo "🚀 Iniciando visualização local..."
./run_viz.sh > viz.log 2>&1 &
VIZ_PID=$!
sleep 3

echo "📊 Dashboard: http://localhost:5173"

if [ "$MODE" = "demo" ]; then
  echo "🧪 Modo demo: simulando evolução e batalhas para validar a UX"
  node viz_server/demo_agents.js > demo.log 2>&1 &
  WORKER_PID=$!
elif [ "$MODE" = "journeys" ]; then
  echo "♾️  Jornadas contínuas: 2 slots, autosave e rotação após Mewtwo"
  "$PYTHON_BIN" run_journeys.py "$@" > training.log 2>&1 &
  WORKER_PID=$!
else
  echo "🧠 Bloco único de treino PPO local iniciado"
  "$PYTHON_BIN" train_hybrid.py "$@" > training.log 2>&1 &
  WORKER_PID=$!
fi

echo "$WORKER_PID" > "$TRAINING_PID_FILE"

wait "$WORKER_PID"
