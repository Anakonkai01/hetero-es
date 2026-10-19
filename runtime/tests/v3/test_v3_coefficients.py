"""
Coefficient rules of Recipe v3 (how rewards become the cᵢ of θ ← θ + α/N·Σ cᵢεᵢ) and the momentum record terms.
zscore@1 must stay today's standardization bit for bit; momentum with a window of 1 must be today's update bit for bit.
"""

import numpy as np
import pytest

from heteroes.es.update import standardize_rewards
from heteroes.v3.coefficients import (
    centered_rank,
    check_rule,
    coefficients_for,
    momentum_inputs,
    python_rule,
    validate_update_rule,
)


def test_zscore_is_todays_standardization():
    rewards = [0.1, 0.0, 1.0, 0.1, 0.1, 0.0]
    got = coefficients_for("zscore@1", rewards, 1e-9)
    assert got.dtype == np.float32 and np.array_equal(got, standardize_rewards(rewards, 1e-9))


def test_centered_rank_spreads_ranks_evenly_and_averages_ties():
    assert centered_rank([3.0, 1.0, 2.0]).tolist() == [0.5, -0.5, 0.0]
    # ties share the mean of their ranks: ranks 0, (1+2)/2, (1+2)/2, 3 over N-1 = 3
    got = centered_rank([0.0, 0.1, 0.1, 1.0])
    assert got.dtype == np.float32 and got.tolist() == pytest.approx([-0.5, 0.0, 0.0, 0.5])
    assert np.array_equal(got, np.float32(np.array([0, 1.5, 1.5, 3]) / 3 - 0.5))
    assert not centered_rank([0.1] * 5).any()  # no signal: a no-op update
    # only the order matters, not the size of the rewards (unlike the z-score)
    assert np.array_equal(centered_rank([1.0, 1000.0, 2.0]), centered_rank([0.1, 0.3, 0.2]))
    with pytest.raises(ValueError):
        centered_rank([1.0, float("nan")])
    assert np.array_equal(coefficients_for("centered-rank@1", [3.0, 1.0, 2.0], 1e-9), centered_rank([3.0, 1.0, 2.0]))


def test_a_python_rule_is_pinned_by_its_code_and_checked():
    digest = "a" * 64
    assert check_rule(python_rule(digest)) == f"python@1:{digest}"
    got = coefficients_for(python_rule(digest), [1.0, 2.0], 1e-9, function=lambda r: [x - 1.5 for x in r])
    assert got.dtype == np.float32 and got.tolist() == [-0.5, 0.5]
    for bad in (lambda r: [0.0], lambda r: [0.0, float("inf")], lambda r: "ab", lambda r: [True, False]):
        with pytest.raises(ValueError):
            coefficients_for(python_rule(digest), [1.0, 2.0], 1e-9, function=bad)
    with pytest.raises(ValueError, match="loaded"):
        coefficients_for(python_rule(digest), [1.0, 2.0], 1e-9)
    for rule in ("zscore@2", "rank@1", "python@1:short", "python@2:" + digest, 1):
        with pytest.raises(ValueError):
            check_rule(rule)


def test_update_rules_are_strict():
    assert validate_update_rule({"kind": "momentum", "beta": 0.875, "window": 4})
    for bad in (
        {"kind": "momentum", "beta": 0.9, "window": 4},  # not exactly a float32
        {"kind": "momentum", "beta": 1.0, "window": 4},
        {"kind": "momentum", "beta": 0.0, "window": 4},
        {"kind": "momentum", "beta": 0.5, "window": 1},
        {"kind": "momentum", "beta": 0.5, "window": 9},
        {"kind": "momentum", "beta": 0.5, "window": 4.0},
        {"kind": "adam", "beta": 0.5, "window": 4},
        {"kind": "momentum", "beta": 0.5},
    ):
        with pytest.raises(ValueError):
            validate_update_rule(bad)


def test_momentum_terms_weight_older_generations_by_beta_and_keep_each_generations_mean():
    rule = {"kind": "momentum", "beta": 0.5, "window": 3}
    current = ([10, 11], np.array([0.25, -0.75], np.float32))
    history = [  # newest first
        {"generation": 4, "seeds": [20, 21, 22, 23], "coefficients": [1.0, -1.0, 0.5, -0.5]},
        {"generation": 3, "seeds": [30, 31], "coefficients": [2.0, 0.0]},
    ]
    seeds, coefficients = momentum_inputs(rule, current, history)
    assert seeds == [30, 31, 20, 21, 22, 23, 10, 11]  # oldest generation first, canonical order inside
    total = len(seeds)
    # apply_coefficients_ divides by the total number of seeds: each term is rescaled so that generation k keeps
    # its own mean over n_k seeds, times beta^age
    expected = [2.0 * 0.25 * total / 2, 0.0]
    expected += [c * 0.5 * total / 4 for c in (1.0, -1.0, 0.5, -0.5)]
    expected += [c * total / 2 for c in (0.25, -0.75)]
    assert coefficients.dtype == np.float32 and coefficients.tolist() == expected


def test_a_window_of_one_or_no_history_is_todays_update_exactly():
    current = ([5, 6, 7], np.array([0.1, -0.3, 0.2], np.float32))
    for rule, history in ((None, []), ({"kind": "momentum", "beta": 0.5, "window": 2}, [])):
        seeds, coefficients = momentum_inputs(rule, current, history)
        assert seeds == [5, 6, 7] and np.array_equal(coefficients, current[1])


def test_momentum_history_must_be_the_previous_generations_in_order():
    rule = {"kind": "momentum", "beta": 0.5, "window": 3}
    current = ([1], np.array([1.0], np.float32))
    entry = {"generation": 4, "seeds": [2], "coefficients": [1.0]}
    with pytest.raises(ValueError):
        momentum_inputs(rule, current, [entry, entry, entry])  # longer than window - 1
    with pytest.raises(ValueError):
        momentum_inputs(rule, current, [entry, {**entry, "generation": 2, "seeds": [3]}])  # not consecutive
    with pytest.raises(ValueError):
        momentum_inputs(rule, current, [{**entry, "coefficients": [0.1]}])  # 0.1 is not a float32 value
    with pytest.raises(ValueError):
        momentum_inputs(rule, current, [{**entry, "seeds": [1]}])  # a seed seen twice
