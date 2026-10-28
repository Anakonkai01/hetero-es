import time, os, sys, numpy as np
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, ".")
from decimal import Decimal
import gen_table as G  # reuses erf/half (recomputes the 63-bit table on import; fine for a prototype)
TOP = 2**31; T = []; i = 0
while True:
    f = int(G.erf((G.half(i) + G.half(i + 1)) / 2 / G.SQRT2) * TOP); T.append(f)
    if f >= TOP - 1: break
    i += 1
T = np.array(T, dtype=np.uint32); TS = np.append(T, np.uint32(2**32 - 1))
print(len(T), "32-bit thresholds, max value", float(np.array([len(T)-1], np.uint16).view(np.float16)[0]))
L = 16; SH = 31 - L
starts = (np.arange(2**L, dtype=np.uint64) << np.uint64(SH))
lo = np.searchsorted(T, starts, side="right"); hi = np.searchsorted(T, starts + np.uint64(2**SH - 1), side="right")
multi = (hi - lo) >= 2; print("flagged buckets %", multi.mean() * 100)
LO = (lo | (multi << 15)).astype(np.uint16)
def exact(raw32):
    idx = np.searchsorted(T, raw32 & np.uint32(0x7FFFFFFF), side="right").astype(np.uint16)
    return (idx | ((raw32 >> np.uint32(31)).astype(np.uint16) << np.uint16(15))).view(np.float16)
BLOCK = int(os.environ.get("BLOCK", 32768))
def sample(raw32):
    n = raw32.size; out = np.empty(n, np.uint16)
    u = np.empty(BLOCK, np.uint32); b = np.empty(BLOCK, np.uint32); e = np.empty(BLOCK, np.uint16); l = np.empty(BLOCK, np.uint16)
    t = np.empty(BLOCK, np.uint32); c = np.empty(BLOCK, bool)
    for s in range(0, n, BLOCK):
        m = min(BLOCK, n - s); r = raw32[s:s+m]; uu, bb, ee, ll, tt, cc, o = u[:m], b[:m], e[:m], l[:m], t[:m], c[:m], out[s:s+m]
        np.bitwise_and(r, np.uint32(0x7FFFFFFF), out=uu)
        np.right_shift(uu, np.uint32(SH), out=bb)
        LO.take(bb, out=ee)
        np.bitwise_and(ee, np.uint16(0x7FFF), out=ll)
        TS.take(ll, out=tt)
        np.greater_equal(uu, tt, out=cc)
        np.add(ll, cc, out=o, casting="unsafe")
        if ee.max() >= 0x8000:
            f = np.flatnonzero(ee >= 0x8000)
            o[f] = np.searchsorted(T, uu[f], side="right")
        np.right_shift(r, np.uint32(31), out=bb); np.left_shift(bb, np.uint32(15), out=bb)
        np.bitwise_or(o, bb, out=o, casting="unsafe")
    return out.view(np.float16)
n = 262144
def raw_for(s): return np.random.PCG64(s).random_raw(n // 2).view(np.uint32)
for s in range(3):
    r = raw_for(s); assert np.array_equal(sample(r).view(np.uint16), exact(r).view(np.uint16))
print("block", BLOCK, "== exact")
t0 = time.perf_counter()
for s in range(40): sample(raw_for(s))
print(f"single {(time.perf_counter()-t0)/40*1e3:.2f} ms")
for w in (4, 8, 16):
    with ThreadPoolExecutor(w) as ex:
        t0 = time.perf_counter(); list(ex.map(lambda s: sample(raw_for(s)), range(800))); a = (time.perf_counter()-t0)/800*1e3
        t0 = time.perf_counter(); list(ex.map(lambda s: np.random.Generator(np.random.PCG64(s)).standard_normal(n, dtype=np.float32).astype(np.float16), range(800))); v1 = (time.perf_counter()-t0)/800*1e3
    print(f"threads {w}: v2 {a:.3f} ms/chunk  v1 {v1:.3f}")
