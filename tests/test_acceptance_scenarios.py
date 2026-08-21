from virinda.core.acceptance import run_all_scenarios, run_scenario


def test_scenario_a_cold_start():
    result = run_scenario("A")
    assert result.passed is True
    assert len(result.assertions) >= 5
    assert len(result.failures) == 0


def test_scenario_b_conversation():
    result = run_scenario("B")
    assert result.passed is True
    assert len(result.records) == 5
    assert len(result.failures) == 0


def test_scenario_c_barge_in_torture():
    result = run_scenario("C")
    assert result.passed is True
    assert len(result.records) == 30
    assert len(result.failures) == 0


def test_scenario_d_soak_and_leak():
    result = run_scenario("D")
    assert result.passed is True
    assert len(result.failures) == 0


def test_scenario_e_desktop_messagebus():
    result = run_scenario("E")
    assert result.passed is True
    assert len(result.failures) == 0


def test_run_all_scenarios():
    results = run_all_scenarios()
    assert len(results) == 5
    assert all(r.passed for r in results)
