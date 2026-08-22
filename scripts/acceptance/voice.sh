#!/usr/bin/env bash
set -euo pipefail

echo "================================================================="
echo "          VirindaAI Voice Acceptance Suite (v0.28.0)    "
echo "================================================================="

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

echo "--> [1/4] Running Full Test Suite..."
uv run pytest -q

echo "--> [2/4] Running Doctor & Audio Diagnostics..."
uv run virinda doctor --audio || true

echo "--> [3/4] Running Voice Benchmark & UX Gate Evaluation..."
uv run virinda benchmark --mock --turns 10

echo "--> [4/4] Running End-to-End Acceptance Scenarios (A through E)..."
uv run virinda acceptance voice "$@"

echo ""
echo "✔ All voice acceptance criteria and end-to-end scenarios passed successfully for v0.28.0!"
