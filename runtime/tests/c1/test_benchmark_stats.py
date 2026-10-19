"""Small statistics for the benchmark summaries: the unit is a RUN (its steady-state mean), never a generation, because the
generations of one run share parent weights, seeds and machines (a pseudo-replicate would make the interval look too narrow)."""
import math

import pytest

from heteroes.benchmark_stats import mean_ci, ratio_ci, t_critical


def test_t_critical_values_are_the_textbook_two_sided_95_percent_ones():
    assert t_critical(1) == pytest.approx(12.706, abs=1e-3)
    assert t_critical(2) == pytest.approx(4.303, abs=1e-3)
    assert t_critical(4) == pytest.approx(2.776, abs=1e-3)
    assert t_critical(9) == pytest.approx(2.262, abs=1e-3)
    assert t_critical(30) == pytest.approx(2.042, abs=1e-3)
    assert t_critical(1000) == pytest.approx(1.96, abs=1e-2)


def test_t_critical_needs_at_least_one_degree_of_freedom():
    with pytest.raises(ValueError):
        t_critical(0)


def test_mean_ci_of_three_values_by_hand():
    # values 10, 12, 14: mean 12, sample stdev 2, sem 2/sqrt(3), half-width t(2) * sem = 4.303 * 1.1547 = 4.969
    mean, half = mean_ci([10.0, 12.0, 14.0])
    assert mean == 12.0
    assert half == pytest.approx(4.303 * 2 / math.sqrt(3), rel=1e-3)


def test_mean_ci_of_one_value_has_no_interval():
    assert mean_ci([5.0]) == (5.0, None)


def test_mean_ci_of_equal_values_has_zero_width():
    assert mean_ci([3.0, 3.0, 3.0]) == (3.0, 0.0)


def test_mean_ci_rejects_empty_input_and_nan():
    with pytest.raises(ValueError):
        mean_ci([])
    with pytest.raises(ValueError):
        mean_ci([1.0, float("nan")])


def test_ratio_ci_point_estimate_is_ratio_of_means():
    ratio, half = ratio_ci([10.0, 10.0, 10.0], [5.0, 5.0, 5.0])
    assert ratio == 2.0
    assert half == 0.0


def test_ratio_ci_widens_with_noise_in_either_series():
    quiet = ratio_ci([100.0, 100.1, 99.9], [100.0, 100.1, 99.9])
    noisy_den = ratio_ci([100.0, 100.1, 99.9], [90.0, 100.0, 110.0])
    noisy_num = ratio_ci([90.0, 100.0, 110.0], [100.0, 100.1, 99.9])
    assert noisy_den[1] > quiet[1] * 10
    assert noisy_num[1] > quiet[1] * 10


def test_ratio_ci_delta_method_by_hand():
    # num: 10, 12, 14 (mean 12, var 4, n 3), den: 4, 6, 8 (mean 6, var 4, n 3); r = 2
    # var(r) ~= r^2 (var_n/(n m_n^2) + var_d/(n m_d^2)) = 4 * (4/(3*144) + 4/(3*36)) = 4 * (0.009259 + 0.037037) = 0.185185
    # df (conservative) = min(n_n, n_d) - 1 = 2 -> t = 4.303; half = 4.303 * sqrt(0.185185) = 1.8517
    ratio, half = ratio_ci([10.0, 12.0, 14.0], [4.0, 6.0, 8.0])
    assert ratio == pytest.approx(2.0)
    assert half == pytest.approx(4.303 * math.sqrt(0.185185), rel=1e-3)


def test_ratio_ci_without_two_values_has_no_interval():
    assert ratio_ci([10.0], [5.0, 5.0]) == (2.0, None)


def test_ratio_ci_rejects_a_zero_denominator():
    with pytest.raises(ValueError):
        ratio_ci([1.0, 2.0], [0.0, 0.0])
