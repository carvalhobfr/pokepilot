#!/bin/bash
# Run the Blue Training Agents
echo "Starting 4 Blue Training Agents..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="$SCRIPT_DIR/../.venv/bin/python"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN="python3"
"$PYTHON_BIN" "$SCRIPT_DIR/train_hybrid.py"
