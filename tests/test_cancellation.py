from virinda.core.cancellation import GenerationController


def test_generation_invalidation_makes_old_work_stale() -> None:
    g = GenerationController()
    first = g.start()
    assert g.is_current(first)
    second = g.invalidate()
    assert second != first
    assert not g.is_current(first)
    assert g.is_current(second)
