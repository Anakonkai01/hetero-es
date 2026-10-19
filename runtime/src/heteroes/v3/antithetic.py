"""
Antithetic pairs (ADR-008 section 5): which (seed, sign) every candidate gets, and the coefficients the update receives.

Candidates 2k and 2k+1 share the seed of pair k with signs +1 and -1. A candidate is perturbed with scale sign * sigma; the
perturbation code only requires a finite scale, and IEEE multiplication is sign-symmetric, so -sigma gives exactly the
negated noise term. For the update each pair is merged into ONE coefficient for its seed,
    c_k = float32((float64(c+) - float64(c-)) / 2),
exact in float64 and rounded once, so that `apply_coefficients_` keeps unique seeds and, dividing by N/2 seeds, makes the
step sum_i s_i c_i eps_i / N. Without antithetic pairs the coefficients pass unchanged: today's update, bit for bit.
"""

import numpy as np

from heteroes.manifest import derive_seed


def candidate_seeds(experiment_id, generation, population, antithetic):
    """(seed, sign) of every candidate of a generation, in canonical candidate order."""
    if type(population) is not int or population < 1:
        raise ValueError(f"population must be a positive integer, got {population!r}")
    if not antithetic:
        return [(derive_seed(experiment_id, generation, index), 1) for index in range(population)]
    if population % 2:
        raise ValueError("an antithetic population must be even")
    return [(derive_seed(experiment_id, generation, pair), sign) for pair in range(population // 2) for sign in (1, -1)]


def merged_update(seeds_and_signs, coefficients):
    """The (seeds, float32 coefficients) to pass to `apply_coefficients_` for candidates in canonical order."""
    coefficients = np.asarray(coefficients)
    if coefficients.ndim != 1 or len(coefficients) != len(seeds_and_signs):
        raise ValueError("one coefficient per candidate")
    if coefficients.dtype != np.float32:
        exact = coefficients.astype(np.float32)
        if not np.array_equal(exact.astype(np.float64), coefficients.astype(np.float64)):
            raise ValueError("coefficients must be float32 values")
        coefficients = exact
    if not np.isfinite(coefficients).all():
        raise ValueError("coefficients must be finite")
    signs = [sign for _, sign in seeds_and_signs]
    if any(sign not in (1, -1) for sign in signs):
        raise ValueError("a sign is +1 or -1")
    if all(sign == 1 for sign in signs):
        return [seed for seed, _ in seeds_and_signs], coefficients
    if len(signs) % 2 or signs != [1, -1] * (len(signs) // 2):
        raise ValueError("antithetic candidates come in (+1, -1) pairs, in order")
    seeds = [seed for seed, _ in seeds_and_signs]
    if seeds[0::2] != seeds[1::2]:
        raise ValueError("the two candidates of a pair share one seed")
    plus, minus = coefficients[0::2].astype(np.float64), coefficients[1::2].astype(np.float64)
    return seeds[0::2], ((plus - minus) / 2).astype(np.float32)
