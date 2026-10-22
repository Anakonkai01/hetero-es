"""Prototype of a libm-free normal sampler (AS241 inverse CDF, float64, own log) vs engine v1 speed."""

import time

import numpy as np

A = (3.3871328727963666080e0, 1.3314166789178437745e2, 1.9715909503065514427e3, 1.3731693765509461125e4,
     4.5921953931549871457e4, 6.7265770927008700853e4, 3.3430575583588128105e4, 2.5090809287301226727e3)
B = (1.0, 4.2313330701600911252e1, 6.8718700749205790830e2, 5.3941960214247511077e3, 2.1213794301586595867e4,
     3.9307895800092710610e4, 2.8729085735721942674e4, 5.2264952788528545610e3)
C = (1.42343711074968357734e0, 4.63033784615654529590e0, 5.76949722146069140550e0, 3.64784832476320460504e0,
     1.27045825245236838258e0, 2.41780725177450611770e-1, 2.27238449892691845833e-2, 7.74545014278341407640e-4)
D = (1.0, 2.05319162663775882187e0, 1.67638483018380384940e0, 6.89767334985100004550e-1, 1.48103976427480074590e-1,
     1.51986665636164571966e-2, 5.47593808499534494600e-4, 1.05075007164441684324e-9)
E = (6.65790464350110377720e0, 5.46378491116411436990e0, 1.78482653991729133580e0, 2.96560571828504891230e-1,
     2.65321895265761230930e-2, 1.24266094738807843860e-3, 2.71155556874348757815e-5, 2.01033439929228813265e-7)
F = (1.0, 5.99832206555887937690e-1, 1.36929880922735805310e-1, 1.48753612908506148525e-2, 7.86869131145613259100e-4,
     1.84631831751005468180e-5, 1.42151175831644588870e-7, 2.04426310338993978564e-15)
LN2_HI, LN2_LO = 6.93147180369123816490e-01, 1.90821492927058770002e-10  # fdlibm split


def horner(coeffs, x):
    acc = np.full_like(x, coeffs[-1])
    for c in coeffs[-2::-1]:
        acc *= x
        acc += c
    return acc


def log_pos(x):
    """log(x) for x > 0 normal float64, with + - * / only (frexp is exact)."""
    m, e = np.frexp(x)  # x = m * 2**e, m in [0.5, 1)
    small = m < 0.70710678118654752440
    m = np.where(small, m * 2.0, m)
    e = (e - small).astype(np.float64)
    s = (m - 1.0) / (m + 1.0)
    z = s * s
    # log(m) = 2 atanh(s) = 2 (s + s^3/3 + ...), |s| <= 0.1716, z <= 0.02944: 12 terms < 1e-19
    series = horner(tuple(1.0 / (2 * k + 1) for k in range(12)), z)
    return e * LN2_HI + (e * LN2_LO + 2.0 * s * series)


def normal_f16(raw):
    k = (raw >> np.uint64(11)).astype(np.int64)
    q = (k * 2 + (1 - 2**53)).astype(np.float64) * 2.0**-54  # (-0.5, 0.5), symmetric, never 0
    aq = np.abs(q)
    out = np.empty_like(q)
    central = aq <= 0.425
    qc = q[central]
    r = 0.180625 - qc * qc
    out[central] = qc * horner(A, r) / horner(B, r)
    tail = ~central
    if tail.any():
        rt = np.sqrt(-log_pos(0.5 - aq[tail]))
        near = rt <= 5.0
        x = np.empty_like(rt)
        a = rt[near] - 1.6
        x[near] = horner(C, a) / horner(D, a)
        b = rt[~near] - 5.0
        x[~near] = horner(E, b) / horner(F, b)
        out[tail] = np.copysign(x, q[tail])
    return out.astype(np.float32).astype(np.float16)


if __name__ == "__main__":
    import statistics

    n = 262144
    gen = np.random.Generator(np.random.PCG64(12345))
    t = time.perf_counter()
    for _ in range(20):
        v1 = np.random.Generator(np.random.PCG64(1)).standard_normal(n, dtype=np.float32).astype(np.float16)
    print("v1 per chunk ms", (time.perf_counter() - t) / 20 * 1e3)
    t = time.perf_counter()
    for _ in range(20):
        raw = np.random.PCG64(1).random_raw(n)
        v2 = normal_f16(raw)
    print("v2 per chunk ms", (time.perf_counter() - t) / 20 * 1e3)
    # accuracy against CPython's AS241 (math.log), in float64 before the casts
    raw = np.random.PCG64(7).random_raw(200000)
    k = (raw >> np.uint64(11)).astype(np.int64)
    q = (k * 2 + (1 - 2**53)).astype(np.float64) * 2.0**-54
    nd = statistics.NormalDist()
    ref = np.array([nd.inv_cdf(0.5 + v) for v in q])
    mine = normal_f16(raw).astype(np.float64)
    print("f16 equal to ref cast", np.mean(ref.astype(np.float32).astype(np.float16) == mine))
    # log accuracy
    xs = np.random.PCG64(3).random_raw(100000).astype(np.float64) / 2.0**64 * 0.075 + 1e-300
    import math
    lr = np.array([math.log(v) for v in xs])
    print("log max rel err", np.max(np.abs(log_pos(xs) - lr) / np.abs(lr)))
    big = np.random.Generator(np.random.PCG64(9)).bit_generator.random_raw(4_000_000)
    s = normal_f16(big).astype(np.float64)
    print("mean", s.mean(), "std", s.std(), "max", np.abs(s).max(), "kurtosis", ((s - s.mean()) ** 4).mean() / s.var() ** 2)
