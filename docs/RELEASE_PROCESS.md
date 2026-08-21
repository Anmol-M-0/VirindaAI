# Release Process

Virinda releases are designed to be reproducible, testable, and easy to audit.

## Version source of truth

The Python package version is defined in `src/virinda/__init__.py` and must match:

- `pyproject.toml`
- `skills/skill-virinda-ai/skill.json`
- `skills/skill-virinda-ai/requirements.txt`
- release documentation
- built wheel metadata

The documentation checker and release validator enforce this consistency.

## Pre-release checklist

Run:

```bash
./scripts/check.sh
./scripts/validate-release.sh
python scripts/verify-ovos-compatibility.py
```

Then build the wheel:

```bash
python -m pip wheel . --no-build-isolation --no-deps -w dist
```

Validate the built metadata and run the full test suite.

## OVOS compatibility

Virinda must not silently move between OVOS release generations. Before changing the OVOS stack:

1. Update the checked-in stable constraints snapshot.
2. Update the compatibility matrix.
3. Test the selected plugins against that snapshot.
4. Update `OVOS_SUPPORTED_STACK.md`.
5. Re-run the compatibility validator.
6. Record the architectural reason in `DECISIONS.md` if the ownership or lifecycle boundary changes.

The upstream OVOS release tracker exists specifically to coordinate compatible package versions through stable/testing/alpha constraint sets.

## Source archive

The source ZIP must not contain generated artifacts such as:

- `__pycache__`
- `*.pyc`
- `.pytest_cache`
- `*.egg-info`
- `build/`
- `dist/`

Release scripts should fail rather than silently producing a dirty archive.

## Release notes

Every release should state:

- user-visible changes
- architecture changes
- compatibility changes
- migration steps
- validation results
- known limitations

Do not claim live hardware validation unless it was performed on real hardware.
