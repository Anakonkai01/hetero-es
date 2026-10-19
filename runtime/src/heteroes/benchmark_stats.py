"""
The few statistics the benchmark summaries need (stdlib only).

The unit of replication is a RUN (the steady-state mean of its generations), not a generation: the generations of one run share the
parent weights, the seeds and the machines, so treating them as independent would make an interval look too narrow (an audit of
G5 found exactly that kind of over-confidence). With few runs the interval is wide on purpose (t with n - 1 degrees of freedom).
"""
import math
import statistics

# two-sided 95 % critical values of Student's t, by degrees of freedom
_T95 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262, 10: 2.228,
        11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145, 15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086,
        25: 2.060, 30: 2.042, 40: 2.021, 60: 2.000, 120: 1.980}


def t_critical(degrees_of_freedom: int) -> float:
    if degrees_of_freedom < 1:
        raise ValueError("degrees of freedom must be >= 1")
    if degrees_of_freedom in _T95:
        return _T95[degrees_of_freedom]
    below = max(k for k in _T95 if k < degrees_of_freedom) if degrees_of_freedom < 120 else None
    if below is None:
        return 1.96
    return _T95[below]          # the table value of the next smaller entry: slightly wider, never narrower


def _check(values) -> list[float]:
    values = [float(v) for v in values]
    if not values:
        raise ValueError("no values")
    if any(math.isnan(v) or math.isinf(v) for v in values):
        raise ValueError("values must be finite")
    return values


def mean_ci(values) -> tuple[float, float | None]:
    """(mean, half-width of the 95 % interval); the half-width is None for a single value."""
    values = _check(values)
    mean = statistics.mean(values)
    if len(values) < 2:
        return mean, None
    sem = statistics.stdev(values) / math.sqrt(len(values))
    return mean, t_critical(len(values) - 1) * sem


def ratio_ci(numerators, denominators) -> tuple[float, float | None]:
    """
    (mean(numerators) / mean(denominators), half-width of its approximate 95 % interval) by the delta method; degrees of freedom
    = the smaller sample size minus 1 (conservative). The half-width is None unless both series have two values.
    """
    num, den = _check(numerators), _check(denominators)
    mean_n, mean_d = statistics.mean(num), statistics.mean(den)
    if mean_d == 0:
        raise ValueError("the denominator has mean 0")
    ratio = mean_n / mean_d
    if mean_n == 0:
        return ratio, None
    if len(num) < 2 or len(den) < 2:
        return ratio, None
    var_n, var_d = statistics.variance(num), statistics.variance(den)
    variance = ratio ** 2 * (var_n / (len(num) * mean_n ** 2) + var_d / (len(den) * mean_d ** 2))
    return ratio, t_critical(min(len(num), len(den)) - 1) * math.sqrt(variance)
