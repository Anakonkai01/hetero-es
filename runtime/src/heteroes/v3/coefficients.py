"""
How the rewards of a generation become the coefficients cᵢ of the update θ ← θ + α/N·Σ cᵢεᵢ, and how a momentum update
is written as one call of `apply_coefficients_` (the kernel does not change; the record carries everything).

Coefficient rules (the `coefficient_rule` of a version-2 generation record):
    zscore@1         (r - mean) / (std + eta): today's rule, `es.update.standardize_rewards`, bit for bit.
    centered-rank@1  rank / (N - 1) - 0.5, ties sharing the mean of their ranks (Salimans et al. 2017): only the order of
                     the rewards matters, so one outlier cannot dominate. Its spread is smaller than the z-score's (about
                     0.29 against 1), so the same alpha is a smaller step.
    python@1:<sha>   a researcher's `f(rewards) -> coefficients`, pinned by the SHA-256 of its source; only a
                     self-hosted coordinator runs it (like a Python scorer, ADR-008 decision 4). Nobody else can recompute
                     it: workers apply the recorded coefficients, as they do for every rule.

Every rule is computed in float64 and rounded to float32 once.

Momentum (truncated heavy ball): step_t = α_t · Σ_{a=0}^{K-1} β^a · g_{t-a}, with g_s = (1/n_s) Σ c_{s,i} ε_{s,i} the update
direction of generation s. The noise of an earlier generation is regenerated from its seeds, so nothing but numbers is
stored: the record of generation t carries the (merged) seeds and coefficients of its K - 1 predecessors. The terms are
joined into one seed list, oldest generation first; since `apply_coefficients_` divides by the total number of seeds M,
a coefficient of generation s becomes c · β^age · M / n_s. A window of 1, or a generation without predecessors, gives the
current inputs unchanged: today's update, bit for bit.
"""

import math
import re

import numpy as np

RULES = ("zscore@1", "centered-rank@1")
_PYTHON = re.compile(r"python@1:[0-9a-f]{64}")
MAX_WINDOW = 8


def python_rule(code_sha256):
    return f"python@1:{code_sha256}"


def check_rule(rule):
    if not isinstance(rule, str) or not (rule in RULES or _PYTHON.fullmatch(rule)):
        raise ValueError(f"unknown coefficient rule {rule!r}")
    return rule


def _rewards(rewards):
    values = np.asarray(rewards, dtype=np.float64)
    if values.ndim != 1 or values.size == 0 or not np.isfinite(values).all():
        raise ValueError("rewards are a nonempty vector of finite numbers")
    return values


def centered_rank(rewards):
    values = _rewards(rewards)
    if values.size == 1:
        return np.zeros(1, dtype=np.float32)
    below = (values[None, :] < values[:, None]).sum(axis=1)
    equal = (values[None, :] == values[:, None]).sum(axis=1)
    ranks = below + (equal - 1) / 2  # the mean rank of a group of ties
    return (ranks / (values.size - 1) - 0.5).astype(np.float32)


def _float32_exact(values, what):
    array = np.asarray(values, dtype=np.float64)
    with np.errstate(over="ignore"):
        rounded = array.astype(np.float32)
    if not np.isfinite(rounded).all():
        raise ValueError(f"{what} must be finite float32 values")
    return rounded


def coefficients_for(rule, rewards, eta, function=None):
    """The float32 coefficients of `rewards` under `rule` (`function` is the loaded code of a python rule)."""
    check_rule(rule)
    if rule == "zscore@1":
        from heteroes.es.update import standardize_rewards

        return standardize_rewards(rewards, eta)
    if rule == "centered-rank@1":
        return centered_rank(rewards)
    if function is None:
        raise ValueError(f"the coefficient rule {rule} must be loaded to compute coefficients")
    values = _rewards(rewards)
    result = function([float(v) for v in values])
    if isinstance(result, (str, bytes)) or not hasattr(result, "__len__") or len(result) != values.size:
        raise ValueError("a coefficient rule returns one number per candidate")
    if any(isinstance(c, (bool, np.bool_)) or not isinstance(c, (int, float, np.integer, np.floating)) for c in result):
        raise ValueError("a coefficient rule returns numbers")
    return _float32_exact([float(c) for c in result], "coefficients")


def validate_update_rule(rule):
    """None (plain step) or {"kind": "momentum", "beta": float32 in (0, 1), "window": 2..MAX_WINDOW}."""
    if rule is None:
        return rule
    if not isinstance(rule, dict) or set(rule) != {"kind", "beta", "window"} or rule["kind"] != "momentum":
        raise ValueError('an update rule is {"kind": "momentum", "beta": ..., "window": ...}')
    beta, window = rule["beta"], rule["window"]
    if (
        isinstance(beta, bool)
        or not isinstance(beta, (int, float))
        or not math.isfinite(beta)
        or not 0 < beta < 1
        or float(np.float32(beta)) != beta
    ):
        raise ValueError("momentum beta is a float32 value strictly between 0 and 1 (for example 0.875)")
    if type(window) is not int or not 2 <= window <= MAX_WINDOW:
        raise ValueError(f"the momentum window is a whole number from 2 to {MAX_WINDOW}")
    return rule


def check_history(rule, generation, history):
    """The momentum history of a record of `generation`: its predecessors, newest first, each with exact float32 coefficients."""
    if rule is None:
        if history:
            raise ValueError("only a momentum record has a history")
        return []
    validate_update_rule(rule)
    if not isinstance(history, (list, tuple)) or len(history) > rule["window"] - 1:
        raise ValueError("a momentum history holds at most window - 1 earlier generations")
    if generation is not None and len(history) != min(rule["window"] - 1, generation):
        raise ValueError("a momentum history holds every earlier generation of its window")
    checked = []
    for age, entry in enumerate(history, start=1):
        if not isinstance(entry, dict) or set(entry) != {"generation", "seeds", "coefficients"}:
            raise ValueError("a history entry is {generation, seeds, coefficients}")
        expected = None if generation is None else generation - age
        if type(entry["generation"]) is not int or (expected is not None and entry["generation"] != expected):
            raise ValueError("the history holds the previous generations in order, newest first")
        if checked and entry["generation"] != checked[-1]["generation"] - 1:
            raise ValueError("the history holds consecutive generations")
        seeds, coefficients = list(entry["seeds"]), list(entry["coefficients"])
        if not seeds or len(seeds) != len(coefficients) or any(type(s) is not int or s < 0 for s in seeds):
            raise ValueError("a history entry has one coefficient per seed")
        exact = _float32_exact(coefficients, "history coefficients")
        if not np.array_equal(exact.astype(np.float64), np.asarray(coefficients, dtype=np.float64)):
            raise ValueError("history coefficients must be exactly float32 values")
        checked.append({"generation": entry["generation"], "seeds": seeds, "coefficients": [float(c) for c in exact]})
    return checked


def momentum_inputs(rule, current, history):
    """(seeds, float32 coefficients) for `apply_coefficients_` of a record whose own merged inputs are `current`."""
    seeds, coefficients = list(current[0]), np.asarray(current[1], dtype=np.float32)
    entries = check_history(rule, None, history)
    if not entries:
        return seeds, coefficients
    beta = np.float64(rule["beta"])
    terms = [(e["seeds"], np.asarray(e["coefficients"], np.float64), age) for age, e in enumerate(entries, start=1)]
    terms = [*reversed(terms), (seeds, coefficients.astype(np.float64), 0)]  # oldest first
    joined = [seed for term_seeds, _, _ in terms for seed in term_seeds]
    if len(set(joined)) != len(joined):
        raise ValueError("a seed appears in two generations of the momentum window")
    total = np.float64(len(joined))
    scaled = np.concatenate([c * beta**age * total / len(s) for s, c, age in terms])
    return joined, _float32_exact(scaled, "momentum coefficients")
