#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
ARCH = (DOCS / "ARCHITECTURE.md").read_text(encoding="utf-8")
ROADMAP = (DOCS / "ROADMAP.md").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")

required_docs = [
    "PRODUCT_NORTH_STAR.md",
    "PRODUCT_GATES.md",
    "ARCHITECTURE.md",
    "JOB_BACKBONE.md",
    "AUDIO_INTERACTIONS.md",
]
missing = [name for name in required_docs if not (DOCS / name).exists()]
if missing:
    raise SystemExit(f"missing product architecture docs: {', '.join(missing)}")

required_phrases = [
    "OVOS MessageBus",
    "JobBroker",
    "NATS JetStream",
    "localhost HTTP overlay is diagnostics-only",
]
for phrase in required_phrases:
    if phrase not in ARCH:
        raise SystemExit(f"architecture drift: missing phrase {phrase!r}")

for phrase in [
    "P0 — Core assistant experience",
    "P1 — Personal assistant",
    "P2 — Safe computer assistant",
    "P3 — Durable background work",
]:
    if phrase not in (DOCS / "PRODUCT_NORTH_STAR.md").read_text(encoding="utf-8"):
        raise SystemExit(f"product hierarchy missing: {phrase}")

# These technologies are deliberately not supported runtime backends.
source_text = "\n".join(
    p.read_text(encoding="utf-8", errors="ignore") for p in (ROOT / "src").rglob("*.py")
)
for forbidden in ("rabbitmq", "pika", "fluvio", "redpanda"):
    if forbidden in source_text.lower():
        raise SystemExit(f"unsupported broker leaked into production source: {forbidden}")

if "NATS JetStream" not in ROADMAP:
    raise SystemExit("roadmap is missing the NATS durable-work boundary")
if "OVOS MessageBus" not in README:
    raise SystemExit("README is missing the OVOS interaction-bus boundary")

print("product direction: PASS")
