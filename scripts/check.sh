#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

for sp in \
    "$SCRIPT_DIR"/.venv/lib/python*/site-packages \
    "$WORKSPACE_ROOT"/VirindAI/.venv/lib/python*/site-packages \
    "$WORKSPACE_ROOT"/chatgpt-cli/.venv/lib/python*/site-packages \
    "$WORKSPACE_ROOT"/nemotron-guard/.venv/lib/python*/site-packages; do
    if [ -d "$sp" ]; then
        export PYTHONPATH="$sp:${PYTHONPATH:-}"
    fi
done

export PYTHONPATH="$SCRIPT_DIR/src:$WORKSPACE_ROOT/chatgpt-cli/src:$WORKSPACE_ROOT/nemotron-guard/src:${PYTHONPATH:-}"

python3 -m compileall -q src tests
python3 -m pytest -q
python3 scripts/verify-ovos-compatibility.py
if command -v ruff >/dev/null 2>&1; then
  ruff check src tests
fi
if command -v cargo >/dev/null 2>&1; then
  cargo check --manifest-path rust/audio-core/Cargo.toml
fi

python3 scripts/check_docs.py
python3 scripts/check_product_direction.py
