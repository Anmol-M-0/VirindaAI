from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
README = ROOT / "README.md"
VERSION_FILE = ROOT / "src" / "virinda" / "__init__.py"
SOURCE_ROOTS = [ROOT / "src", ROOT / "scripts", ROOT / "config", ROOT / "deploy", ROOT / "skills"]
SOURCE_FILES = [
    path for source_root in SOURCE_ROOTS for path in source_root.rglob("*.*") if path.is_file()
]
ENV_NAMES = set(
    re.findall(
        r"VIRINDA_[A-Z0-9_]+",
        "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in SOURCE_FILES),
    )
)
VERSION = re.search(r'__version__\s*=\s*"([^"]+)"', VERSION_FILE.read_text(encoding="utf-8")).group(
    1
)

errors: list[str] = []

md_files = sorted([README, *DOCS.rglob("*.md")])
for path in md_files:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not re.search(r"^#\s+\S", text, flags=re.M):
        errors.append(f"{path.relative_to(ROOT)}: missing top-level heading")
    if "turn0" in text or "turn1" in text or "sandbox:/" in text:
        errors.append(f"{path.relative_to(ROOT)}: contains internal/non-source citation marker")
    for match in re.finditer(r"\]\(([^)#]+)(?:#[^)]+)?\)", text):
        target = match.group(1)
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        target_path = (path.parent / target).resolve()
        if not target_path.exists():
            errors.append(f"{path.relative_to(ROOT)}: broken local link -> {target}")

# Public environment variables must be documented at least once.
config_doc = (DOCS / "CONFIGURATION.md").read_text(encoding="utf-8")
missing_env = sorted(name for name in ENV_NAMES if name not in config_doc)
for name in missing_env:
    errors.append(f"CONFIGURATION.md: missing environment variable {name}")

# README should advertise the current release and docs index.
readme = README.read_text(encoding="utf-8")
if f"v{VERSION}" not in readme:
    errors.append(f"README.md: current version v{VERSION} not mentioned")
if "docs/README.md" not in readme and "Documentation" not in readme:
    errors.append("README.md: documentation navigation is missing")

# Avoid duplicate stale package versions in the public source tree.
for path in [README, *DOCS.rglob("*.md"), ROOT / "CHANGELOG.md", ROOT / "RELEASE.md"]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    versions = set(re.findall(r"\bv(0\.\d+\.\d+)\b", text))
    stale = sorted(v for v in versions if v != VERSION)
    if stale and path.name not in {"CHANGELOG.md", "RELEASE.md"}:
        errors.append(f"{path.relative_to(ROOT)}: stale release version(s): {', '.join(stale)}")

if errors:
    print("Documentation validation failed:")
    for error in errors:
        print(f"- {error}")
    raise SystemExit(1)

print(
    f"Documentation validation passed: {len(md_files)} markdown files, version v{VERSION}, {len(ENV_NAMES)} environment variables checked"
)
