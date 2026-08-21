# Documentation Policy

Documentation is part of the implementation contract in VirindaAI.

## Required documentation for public behavior

A change is incomplete if it modifies any of the following without updating documentation:

- CLI commands
- IPC methods/events
- environment variables
- OVOS configuration
- service files/installation behavior
- persistence schema or retention
- security authority
- user-visible feature behavior
- compatibility constraints

## Documentation quality gate

The repository includes a documentation validator that checks:

- every Markdown document has a top-level title;
- local Markdown links resolve;
- no internal tool/citation markers remain in local source documents;
- documented environment variables cover variables referenced by source/scripts/configuration;
- the current release version is consistent where version is intentionally stated;
- README navigation points to the canonical document set.

Run:

```bash
python scripts/check_docs.py
```

## Stable wording

Use “implemented” only when there is a real implementation and automated coverage. Use “validated” only when the relevant runtime/environment was actually exercised. Use “supported” only when the compatibility matrix and acceptance path are defined.

Hardware-dependent claims must identify the hardware/runtime layer that was tested.
