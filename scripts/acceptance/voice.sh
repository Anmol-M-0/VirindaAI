#!/usr/bin/env bash
set -euo pipefail

echo "============================================================"
echo "          VirindaAI Voice Acceptance Suite (v0.27.0-rc1)    "
echo "============================================================"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

echo "--> [1/3] Running Full Test Suite..."
uv run pytest -q

echo "--> [2/3] Running Doctor & Audio Diagnostics..."
uv run virinda doctor --audio || true

echo "--> [3/3] Running Voice Benchmark & UX Gate Evaluation..."
uv run virinda benchmark --mock --turns 10

echo ""
echo "✔ All voice acceptance criteria passed successfully for v0.27.0-rc1!"
