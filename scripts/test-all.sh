#!/bin/bash
# Run all tests for SentinelWatch
# Usage: ./scripts/test-all.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "==================================="
echo "Running SentinelWatch Tests"
echo "==================================="

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Test backend
echo -e "${YELLOW}Testing backend...${NC}"
cd "$PROJECT_ROOT/backend"

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate
pip install -e ".[dev,sqlite]" > /dev/null 2>&1

echo "Running pytest..."
python -m pytest tests/ -v --tb=short
BACKEND_RESULT=$?

# Test frontend
echo -e "${YELLOW}Testing frontend...${NC}"
cd "$PROJECT_ROOT/frontend"

if [ ! -d "node_modules" ]; then
    echo "Installing dependencies..."
    npm install
fi

echo "Running vitest..."
npm run test:run
FRONTEND_RESULT=$?

# Test agent
echo -e "${YELLOW}Testing agent...${NC}"
cd "$PROJECT_ROOT/agent"

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate
pip install -e ".[dev]" > /dev/null 2>&1

echo "Running pytest..."
python -m pytest tests/ -v --tb=short
AGENT_RESULT=$?

# Summary
echo -e "${YELLOW}===================================${NC}"
echo -e "${YELLOW}Test Summary${NC}"
echo -e "${YELLOW}===================================${NC}"

if [ $BACKEND_RESULT -eq 0 ]; then
    echo -e "${GREEN}✓ Backend tests passed${NC}"
else
    echo -e "${RED}✗ Backend tests failed${NC}"
fi

if [ $FRONTEND_RESULT -eq 0 ]; then
    echo -e "${GREEN}✓ Frontend tests passed${NC}"
else
    echo -e "${RED}✗ Frontend tests failed${NC}"
fi

if [ $AGENT_RESULT -eq 0 ]; then
    echo -e "${GREEN}✓ Agent tests passed${NC}"
else
    echo -e "${RED}✗ Agent tests failed${NC}"
fi

# Exit with error if any test failed
if [ $BACKEND_RESULT -ne 0 ] || [ $FRONTEND_RESULT -ne 0 ] || [ $AGENT_RESULT -ne 0 ]; then
    exit 1
fi

echo -e "${GREEN}All tests passed!${NC}"
