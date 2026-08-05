#!/bin/bash
# Start Everything: Visualization Server + React Dashboard + 4 Blue Agents

# Function to kill all background processes on exit
cleanup() {
    echo "🛑 Shutting down..."
    # Kill all child processes of this script
    pkill -P $$ 
    # Also force kill specific ports just in case
    lsof -ti:3000 | xargs kill -9 2>/dev/null
    lsof -ti:3344 | xargs kill -9 2>/dev/null
    lsof -ti:5173 | xargs kill -9 2>/dev/null
    pkill -f train_hybrid.py
    exit
}

# Trap SIGINT (Ctrl+C) and call cleanup
trap cleanup SIGINT

echo "🚀 Starting PokeAI Blue System..."

# 1. Start Visualization (WebSocket + React Frontend)
# We run this in background but pipe output to a log to keep terminal clean
echo "   - Starting Visualization Server..."
./run_viz.sh > viz.log 2>&1 &
VIZ_PID=$!

# Wait a bit for server to initialize
sleep 5

# 2. Start Agents
echo "   - Starting 4 Blue Agents..."
./run_blue_agents.sh &
AGENTS_PID=$!

echo "✅ System Started!"
echo "   - Dashboard: http://localhost:5173"
echo "   - Logs: tail -f viz.log"
echo "   - Press Ctrl+C to stop everything."

# Wait for both processes
wait $VIZ_PID $AGENTS_PID
