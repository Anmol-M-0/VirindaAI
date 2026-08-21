from __future__ import annotations

from typing import Callable

from virinda.core.acceptance.models import AcceptanceResult
from virinda.core.acceptance.scenarios.barge_in import run_barge_in_torture_scenario
from virinda.core.acceptance.scenarios.cold_start import run_cold_start_scenario
from virinda.core.acceptance.scenarios.conversation import run_conversation_scenario
from virinda.core.acceptance.scenarios.desktop import run_desktop_scenario
from virinda.core.acceptance.scenarios.soak import run_soak_scenario

SCENARIOS: dict[str, Callable[[], AcceptanceResult]] = {
    "A": run_cold_start_scenario,
    "B": run_conversation_scenario,
    "C": run_barge_in_torture_scenario,
    "D": run_soak_scenario,
    "E": run_desktop_scenario,
}


def run_scenario(name: str) -> AcceptanceResult:
    key = name.upper().strip()
    if key in SCENARIOS:
        return SCENARIOS[key]()
    raise ValueError(f"Unknown acceptance scenario: {name}. Available: {list(SCENARIOS.keys())}")


def run_all_scenarios() -> list[AcceptanceResult]:
    return [fn() for fn in SCENARIOS.values()]
