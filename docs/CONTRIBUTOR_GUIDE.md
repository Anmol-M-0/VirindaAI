# Contributor Guide

Marina is intentionally layered. New code should enter the smallest layer that owns the behavior.

## Where code belongs

| Need | Location |
|---|---|
| domain contract/value | `src/marina/domain/` |
| state/cancellation/event primitive | `src/marina/core/` |
| orchestration | `src/marina/application/` |
| persistence/provider adapter | `src/marina/infrastructure/` |
| CLI/IPC/GUI edge | `src/marina/interfaces/` or `desktop.py` |
| OVOS integration | `src/marina/ovos/` and `skills/` |
| feature bundle | `src/marina/features.py` or a future dedicated feature module |
| tests | `tests/` |
| deployment | `deploy/`, `scripts/`, `config/ovos/` |
| architecture decisions | `docs/DECISIONS.md` |

## Design rules

1. Prefer protocols over concrete cross-layer dependencies.
2. Keep the application service authoritative.
3. Make cancellation generation-safe.
4. Do not block the OVOS message bus or real-time audio callbacks.
5. Keep SQLite access behind a store/feature boundary.
6. Treat tool execution as privileged capability, not natural-language convenience.
7. Make private mode a policy input to every feature that persists or captures data.
8. Add a regression test for every bug fix.
9. Update documentation in the same change as public behavior.
10. Never claim a real hardware integration was tested if only mocks were used.

## Adding a tool

Every tool must define:

- stable name
- description
- risk class
- input schema
- authority required
- audit behavior
- failure semantics
- privacy implications
- test coverage

Do not add arbitrary shell execution as a generic escape hatch.

## Adding an OVOS integration

Before adding a repository:

1. Determine whether it is in the stable constraints file.
2. Check its release/channel relationship with the current stable profile.
3. Decide whether it belongs in the stable base or Marina-specific add-ons.
4. Add the dependency and compatibility rule.
5. Add an environment smoke test.
6. Add a live-runtime probe when possible.
7. Document ownership and failure behavior.

## Documentation requirement

A public feature is not complete until its documentation explains what it does, how to configure it, what it persists, how it fails, and how to disable it.
