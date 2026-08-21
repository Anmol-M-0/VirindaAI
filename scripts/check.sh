#!/usr/bin/env bash
set -euo pipefail
export PYTHONPATH="${PYTHONPATH:-}:$(pwd)/src"
python -m compileall -q src tests
pytest -q
python scripts/verify-ovos-compatibility.py
if command -v ruff >/dev/null 2>&1; then
  ruff check src tests
fi
if command -v cargo >/dev/null 2>&1; then
  cargo check --manifest-path rust/audio-core/Cargo.toml
fi

python scripts/check_docs.py
python scripts/check_product_direction.py
