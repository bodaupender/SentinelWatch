#!/bin/bash
# Run all linting for SentinelWatch
# Usage: ./scripts/lint-all.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "==================================="
echo "Running SentinelWatch Linting"
echo "==================================="

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Lint backend
echo -e "${YELLOW}Linting backend...${NC}"
cd "$PROJECT_ROOT/backend"

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate
pip install -e ".[dev,sqlite]" > /dev/null 2>&1

echo "Running ruff..."
ruff check src/ tests/
RUFF_RESULT=$?

echo "Running mypy..."
mypy src/
MYPY_RESULT=$?

echo "Running bandit..."
bandit -r src/
BANDIT_RESULT=$?

# Lint frontend
echo -e "${YELLOW}Linting frontend...${NC}"
cd "$PROJECT_ROOT/frontend"

if [ ! -d "node_modules" ]; then
    echo "Installing dependencies..."
    npm install
fi

echo "Running ESLint..."
npm run lint
ESLINT_RESULT=$?

echo "Running Prettier check..."
npm run format:check
PRETTIER_RESULT=$?

echo "Running TypeScript type check..."
npm run typecheck
TSC_RESULT=$?

# Lint agent
echo -e "${YELLOW}Linting agent...${NC}"
cd "$PROJECT_ROOT/agent"

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate
pip install -e ".[dev]" > /dev/null 2>&1

echo "Running ruff..."
ruff check src/ tests/
AGENT_RUFF_RESULT=$?

echo "Running mypy..."
mypy src/
AGENT_MYPY_RESULT=$?

echo "Running bandit..."
bandit -r src/
AGENT_BANDIT_RESULT=$?

# Summary
echo -e "${YELLOW}===================================${NC}"
echo -e "${YELLOW}Linting Summary${NC}"
echo -e "${YELLOW}===================================${NC}"

ALL_PASSED=true

check_result() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✓ $2${NC}"
    else
        echo -e "${RED}✗ $2${NC}"
        ALL_PASSED=false
    fi
}

check_result $RUFF_RESULT "Backend ruff"
check_result $MYPY_RESULT "Backend mypy"
check_result $BANDIT_RESULT "Backend bandit"
check_result $ESLINT_RESULT "Frontend ESLint"
check_result $PRETTIER_RESULT "Frontend Prettier"
check_result $TSC_RESULT "Frontend TypeScript"
check_result $AGENT_RUFF_RESULT "Agent ruff"
check_result $AGENT_MYPY_RESULT "Agent mypy"
check_result $AGENT_BANDIT_RESULT "Agent bandit"

if [ "$ALL_PASSED" = true ]; then
    echo -e "${GREEN}All linting passed!${NC}"
    exit 0
else
    echo -e "${RED}Some linting checks failed${NC}"
    exit 1
fi
