#!/bin/bash
cd "$(dirname "$0")"

echo "🤖 Starting AI Strategy API Server..."
PYTHON_BIN="../.venv/bin/python"
[ -x "$PYTHON_BIN" ] || PYTHON_BIN="python3"
"$PYTHON_BIN" ai_api_server.py
