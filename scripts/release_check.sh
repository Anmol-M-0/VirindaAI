#!/usr/bin/env bash
# ==============================================================================
# release_check.sh - VirindaAI Production Release Validation Gate (v0.27.0)
# ==============================================================================
# Validates packaging, isolated installation, database migrations, systemd units,
# and voice acceptance scenarios on built release artifacts.
# ==============================================================================

set -euo pipefail

# ANSI color codes
GREEN="\033[0;32m"
BLUE="\033[0;34m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
BOLD="\033[1m"
NC="\033[0m"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "================================================================="
echo -e "       ${BOLD}VirindaAI Production Release Gate (v0.27.0)${NC}      "
echo "================================================================="

echo ""
echo -e "--> ${BLUE}[1/6] Running Repository & Source Checks...${NC}"
uv run ./scripts/check.sh

echo ""
echo -e "--> ${BLUE}[2/6] Running Full Test Suite...${NC}"
uv run pytest -q

echo ""
echo -e "--> ${BLUE}[3/6] Building Packaging Artifacts (Wheel & Sdist)...${NC}"
rm -rf dist/ build/
uv build

echo ""
echo -e "--> ${BLUE}[4/6] Validating Isolated Installation & Clean-Machine Execution...${NC}"
TEST_VENV="$(mktemp -d /tmp/virinda-release-test-XXXXXX)"
cleanup() {
    rm -rf "$TEST_VENV"
}
trap cleanup EXIT

python3 -m venv "$TEST_VENV"
WHEEL_FILE="$(find "$REPO_ROOT/dist" -name "virinda*.whl" | head -n 1)"
echo "  Installing $WHEEL_FILE into isolated environment: $TEST_VENV"
"$TEST_VENV/bin/pip" install --quiet "$WHEEL_FILE"

# Execute tests from /tmp to ensure no local source tree imports
echo "  Testing installed CLI binary outside workspace..."
(
    cd /tmp
    "$TEST_VENV/bin/virinda" --help >/dev/null
    "$TEST_VENV/bin/virinda" status >/dev/null
    "$TEST_VENV/bin/virinda" benchmark voice --mock --turns 2 >/dev/null
)
echo -e "  ${GREEN}✔${NC} Isolated package execution verified."

echo ""
echo -e "--> ${BLUE}[5/6] Validating SQLite Schema Migrations & Systemd Units...${NC}"
uv run pytest tests/test_sqlite_migration_safety.py tests/test_systemd_lifecycle.py -q
echo -e "  ${GREEN}✔${NC} SQLite migration safety and systemd unit verification passed."

echo ""
echo -e "--> ${BLUE}[6/6] Executing Voice Acceptance Scenarios (A through E)...${NC}"
uv run virinda acceptance voice

echo ""
echo "================================================================="
echo -e "               ${GREEN}${BOLD}RELEASE CHECK: 100% PASS${NC}               "
echo "================================================================="
echo "Generated Release Artifacts:"
ls -lh "$REPO_ROOT/dist"
echo ""
echo "SHA256 Checksums:"
sha256sum "$REPO_ROOT/dist/"*
echo "================================================================="
