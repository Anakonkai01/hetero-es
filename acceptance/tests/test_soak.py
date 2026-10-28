from acceptance.soak import growth_failure


def thirds(early, middle, late):
    return {name: {"total_seconds": value} for name, value in zip(("early", "middle", "late"), (early, middle, late))}


def test_flat_bookkeeping_passes():
    assert growth_failure(thirds(1.03, 0.99, 0.98), limit=1.5) is None  # the 2026-10-27 soak


def test_growth_like_the_old_product_runner_fails():
    message = growth_failure(thirds(1.7, 5.0, 11.0), limit=1.5)  # the unexplained 1.7 s -> 11 s growth
    assert message and "11" in message and "1.7" in message


def test_the_limit_is_inclusive_and_relative_to_the_early_third():
    assert growth_failure(thirds(2.0, 2.0, 3.0), limit=1.5) is None
    assert growth_failure(thirds(2.0, 2.0, 3.01), limit=1.5) is not None


def test_a_run_too_short_for_three_thirds_cannot_pass():
    assert growth_failure({"early": {"total_seconds": 1.0}}, limit=1.5) is not None
