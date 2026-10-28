"""T_i = floor(2**63 * erf(m_i / sqrt 2)), m_i = midpoint of the positive fp16 values with bits i and i+1 (decimal, 60 digits)."""
import time, numpy as np
from decimal import Decimal, getcontext
getcontext().prec = 60
def pi():
    getcontext().prec += 2
    three = Decimal(3); lasts, t, s, n, na, d, da = 0, three, 3, 1, 0, 0, 24
    while s != lasts:
        lasts = s; n, na = n + na, na + 8; d, da = d + da, da + 32; t = (t * n) / d; s += t
    getcontext().prec -= 2
    return +s
SQRT_PI = pi().sqrt(); SQRT2 = Decimal(2).sqrt()
def erf(x):  # 2/sqrt(pi) e^{-x^2} sum 2^n x^{2n+1} / (1*3*...*(2n+1)): positive terms, no cancellation
    x2 = x * x; term = x; total = x; n = 0
    while True:
        n += 1; term = term * 2 * x2 / (2 * n + 1)
        if term < total * Decimal(10) ** -58: break
        total += term
    return 2 / SQRT_PI * (-x2).exp() * total
def half(i): return Decimal(float(np.array([i], np.uint16).view(np.float16)[0]))
TOP = 2**63
t0 = time.time(); T = []; margins = []
i = 0
while True:
    m = (half(i) + half(i + 1)) / 2
    v = erf(m / SQRT2) * TOP
    f = int(v); margins.append(min(v - f, f + 1 - v))
    T.append(f)
    if f >= TOP - 1: break
    i += 1
print(len(T), "thresholds, last value bits", i, float(half(i)), "min margin", min(margins), "secs", time.time() - t0)
np.save("v2_thresholds.npy", np.array(T, dtype=np.uint64))
