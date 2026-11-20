#!/bin/bash
# Development environment stop script for SentinelWatch
# Usage: ./scripts/dev-stop.sh

set -e

echo "==================================="
echo "Stopping SentinelWatch Development Environment"
echo "==================================="

# Kill backend
if [ -f /tmp/sentinelwatch_backend.pid ]; then
    BACKEND_PID=$(cat /tmp/sentinelwatch_backend.pid)
    if kill -0 $BACKEND_PID 2>/dev/null; then
        echo "Stopping backend (PID: $BACKEND_PID)..."
        kill $BACKEND_PID
    fi
    rm /tmp/sentinelwatch_backend.pid
fi

# Kill frontend
if [ -f /tmp/sentinelwatch_frontend.pid ]; then
    FRONTEND_PID=$(cat /tmp/sentinelwatch_frontend.pid)
    if kill -0 $FRONTEND_PID 2>/dev/null; then
        echo "Stopping frontend (PID: $FRONTEND_PID)..."
        kill $FRONTEND_PID
    fi
    rm /tmp/sentinelwatch_frontend.pid
fi

# Also kill any remaining processes on our ports
echo "Cleaning up any remaining processes on ports 8000 and 3000..."
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
lsof -ti:3000 | xargs kill -9 2>/dev/null || true

echo "Development environment stopped."
