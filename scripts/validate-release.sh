#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

python - <<'PY'
import json
from pathlib import Path
import virinda

root = Path.cwd()
assert virinda.__version__ == json.loads((root / 'skills/skill-virinda-ai/skill.json').read_text())['version']
assert json.loads((root / "config/ovos/mycroft.conf.example.json").read_text())['stt']['module'] == 'ovos-stt-plugin-whispercpp'
p = json.loads((root / "config/ovos/virinda-persona.json").read_text())
assert p['solvers'] == ['ovos-solver-openai-plugin']
skill = json.loads((root / "skills/skill-virinda-ai/skill.json").read_text())
assert skill['version'] == virinda.__version__
print('release metadata: OK')
PY

pytest -q
python -m compileall -q src tests

if command -v ruff >/dev/null 2>&1; then ruff check src tests; fi
if command -v cargo >/dev/null 2>&1; then cargo check --manifest-path rust/audio-core/Cargo.toml; fi

printf '%s\n' 'release validation: OK'
