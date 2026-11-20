#!/bin/bash
# Development environment startup script for SentinelWatch
# Usage: ./scripts/dev-start.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "==================================="
echo "Starting SentinelWatch Development Environment"
echo "==================================="

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"

if ! command_exists python3; then
    echo -e "${RED}Python 3 not found. Please install Python 3.12+${NC}"
    exit 1
fi

if ! command_exists node; then
    echo -e "${RED}Node.js not found. Please install Node.js 20+${NC}"
    exit 1
fi

if ! command_exists npm; then
    echo -e "${RED}npm not found. Please install npm${NC}"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "${GREEN}✓ Python ${PYTHON_VERSION}${NC}"

NODE_VERSION=$(node --version)
echo -e "${GREEN}✓ Node.js ${NODE_VERSION}${NC}"

# Start backend
echo -e "${YELLOW}Starting backend...${NC}"
cd "$PROJECT_ROOT/backend"

if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

if [ ! -f "config/backend.yaml" ]; then
    echo "Creating backend config from example..."
    cp config/backend.yaml.example config/backend.yaml
fi

pip install -e ".[dev,sqlite]" > /dev/null 2>&1

# Run database migrations (when available)
# python -m alembic upgrade head

# Start backend in background
echo "Starting backend server on http://localhost:8000"
python -m sentinelwatch_backend.main --reload &
BACKEND_PID=$!

# Wait for backend to start
sleep 3

# Start frontend
echo -e "${YELLOW}Starting frontend...${NC}"
cd "$PROJECT_ROOT/frontend"

if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies..."
    npm install
fi

echo "Starting frontend dev server on http://localhost:3000"
npm run dev &
FRONTEND_PID=$!

# Save PIDs for cleanup
echo $BACKEND_PID > /tmp/sentinelwatch_backend.pid
echo $FRONTEND_PID > /tmp/sentinelwatch_frontend.pid

echo -e "${GREEN}===================================${NC}"
echo -e "${GREEN}Development environment started!${NC}"
echo -e "${GREEN}===================================${NC}"
echo ""
echo "Backend:  http://localhost:8000"
echo "API Docs: http://localhost:8000/docs"
echo "Frontend: http://localhost:3000"
echo ""
echo "Press Ctrl+C to stop all services"

# Wait for interrupt
trap "echo 'Stopping...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM
wait
