#!/usr/bin/env python3
"""Verify Marina's stable OVOS profile against the checked-in OVOS lock."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def cmap(path):
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[<>=!~]", line, maxsplit=1)[0].strip().lower().replace("_", "-")
        out[name] = line[len(name) :]
    return out


def py_spec(text, pkg):
    m = re.search(rf'"{re.escape(pkg)}([^"]*)"', text, re.I)
    return m.group(1) if m else None


def main():
    matrix = json.loads((ROOT / "config/ovos/compatibility.json").read_text())
    stable = cmap(ROOT / matrix["stable_channel"]["constraints_file"])
    py = (ROOT / "pyproject.toml").read_text()
    failures = []
    for pkg, spec in matrix["stable_channel"]["required"].items():
        if stable.get(pkg) != spec:
            failures.append(f"stable constraint mismatch: {pkg} {stable.get(pkg)!r} != {spec!r}")
        if py_spec(py, pkg) != spec:
            failures.append(f"pyproject mismatch: {pkg}")
    for pkg, spec in matrix["stable_channel"].get("supported_stack", {}).items():
        if stable.get(pkg) != spec:
            failures.append(
                f"stable supported-stack mismatch: {pkg} {stable.get(pkg)!r} != {spec!r}"
            )
    policy = matrix.get("reliability_policy", {})
    tier_a = set(policy.get("tier_a_production", []))
    tier_b = set(policy.get("tier_b_stable_local_fallback", []))
    tier_c = set(policy.get("tier_c_marina_addons", []))
    tier_d = set(policy.get("tier_d_experimental_or_legacy", []))
    if len(tier_a | tier_b | tier_c | tier_d) != len(tier_a) + len(tier_b) + len(tier_c) + len(
        tier_d
    ):
        failures.append("reliability tiers overlap")
    overrides = (ROOT / matrix["audio_addons"]["constraints_file"]).read_text()
    for group in ("stable_plugin_pins", "extra_pins"):
        for pkg, pin in matrix["audio_addons"][group].items():
            if f"{pkg}{pin}" not in overrides:
                failures.append(f"override missing: {pkg}{pin}")
    for pkg in matrix["audio_addons"]["extra_pins"]:
        if pkg in stable:
            failures.append(f"extra addon unexpectedly appears in stable lock: {pkg}")
    if failures:
        print("OVOS compatibility: FAIL")
        print("\n".join(failures))
        return 1
    print("OVOS compatibility: PASS")
    print("Stable OVOS lock + Marina audio overrides are internally consistent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
