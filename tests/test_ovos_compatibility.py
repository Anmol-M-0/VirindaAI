import json
import re
from pathlib import Path


def _constraint_map(path: Path) -> dict[str, str]:
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[<>=!~]", line, maxsplit=1)[0].strip().lower().replace("_", "-")
        result[name] = line[len(name) :]
    return result


def test_checked_in_stable_constraints_match_marina_matrix():
    root = Path(__file__).parents[1]
    matrix = json.loads((root / "config/ovos/compatibility.json").read_text(encoding="utf-8"))
    stable = _constraint_map(root / matrix["stable_channel"]["constraints_file"])
    for package, expected in matrix["stable_channel"]["required"].items():
        assert stable[package] == expected


def test_stable_plugin_pins_fit_inside_ovos_stable_lock():
    root = Path(__file__).parents[1]
    matrix = json.loads((root / "config/ovos/compatibility.json").read_text(encoding="utf-8"))
    stable = _constraint_map(root / matrix["stable_channel"]["constraints_file"])
    overrides = (root / matrix["audio_addons"]["constraints_file"]).read_text(encoding="utf-8")
    for package, pin in matrix["audio_addons"]["stable_plugin_pins"].items():
        assert package in stable
        assert f"{package}{pin}" in overrides


def test_extra_audio_addons_are_not_silently_added_to_stable_lock():
    root = Path(__file__).parents[1]
    matrix = json.loads((root / "config/ovos/compatibility.json").read_text(encoding="utf-8"))
    stable = _constraint_map(root / matrix["stable_channel"]["constraints_file"])
    overrides = (root / matrix["audio_addons"]["constraints_file"]).read_text(encoding="utf-8")
    for package, pin in matrix["audio_addons"]["extra_pins"].items():
        assert package not in stable
        assert f"{package}{pin}" in overrides


def test_experimental_agent_requirements_cannot_match_stable_persona_stack():
    root = Path(__file__).parents[1]
    matrix = json.loads((root / "config/ovos/compatibility.json").read_text(encoding="utf-8"))
    stable = matrix["stable_channel"]["required"]
    experimental = matrix["experimental_agent"]["requires"]
    assert stable["ovos-persona"] != experimental["ovos-persona"]
    assert stable["ovos-plugin-manager"] != experimental["ovos-plugin-manager"]
    assert stable["ovos-openai-plugin"] != experimental["ovos-openai-plugin"]


def test_reliability_tiers_are_disjoint_and_supported_stack_is_in_stable_lock():
    root = Path(__file__).parents[1]
    matrix = json.loads((root / "config/ovos/compatibility.json").read_text(encoding="utf-8"))
    stable = _constraint_map(root / matrix["stable_channel"]["constraints_file"])
    tiers = matrix["reliability_policy"]
    names = [
        "tier_a_production",
        "tier_b_stable_local_fallback",
        "tier_c_marina_addons",
        "tier_d_experimental_or_legacy",
    ]
    sets = [set(tiers[name]) for name in names]
    assert sum(map(len, sets)) == len(set().union(*sets))
    for package, expected in matrix["stable_channel"]["supported_stack"].items():
        assert stable[package] == expected


def test_stable_tier_never_contains_explicit_addons_or_experimental_projects():
    root = Path(__file__).parents[1]
    matrix = json.loads((root / "config/ovos/compatibility.json").read_text(encoding="utf-8"))
    tiers = matrix["reliability_policy"]
    stable = set(tiers["tier_a_production"]) | set(tiers["tier_b_stable_local_fallback"])
    assert "ovos-stt-plugin-whispercpp" not in stable
    assert "phoonnx" not in stable
    assert "ovos-chat-openai-plugin" not in stable
