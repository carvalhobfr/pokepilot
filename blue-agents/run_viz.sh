#!/bin/bash
# Run the Map Visualization Server for Blue Agents

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "Starting Blue Map Visualization Server"
echo "=========================================="

# Check if node is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js not found! Please install Node.js to run the visualization."
    echo "   brew install node"
    exit 1
fi

# Install dependencies if needed
if [ ! -d "dashboard-react/node_modules" ]; then
    echo "📦 Installing React dependencies..."
    cd dashboard-react && npm install && cd ..
fi

# Start the WebSocket server
echo "🚀 Starting WebSocket Server..."
lsof -ti:3344 | xargs kill -9 2>/dev/null
node viz_server/ws_relay.js &
WS_PID=$!

# Start React Dev Server
echo "🚀 Starting React Dashboard..."
echo "   Open http://localhost:5173 to view the map"
cd dashboard-react && npm run dev -- --host 127.0.0.1 &
REACT_PID=$!

# Cleanup on exit
trap "kill $WS_PID $REACT_PID" EXIT
wait
