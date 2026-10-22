import numpy as np
M128 = (1 << 128) - 1
MULT = 0x2360ED051FC65DA44385DF649FCCF645  # PCG 128-bit default multiplier
def xsl_rr(s):
    hi, lo = s >> 64, s & ((1 << 64) - 1)
    x = hi ^ lo; r = hi >> 58
    return ((x >> r) | (x << ((64 - r) & 63))) & ((1 << 64) - 1)
seed = 0x1234567890ABCDEF1234567890ABCDEF
g = np.random.PCG64(seed)
st = g.state['state']; s0, inc = st['state'], st['inc']
ref = np.random.PCG64(seed).random_raw(10)
s = s0; out = []
for _ in range(10):
    s = (s * MULT + inc) & M128; out.append(xsl_rr(s))
print(all(int(a) == b for a, b in zip(ref, out)))
# jump-ahead: state_m = A_m*s0 + B_m*inc
A, B = 1, 0
for m in range(1, 11):
    A, B = (A * MULT) & M128, (B * MULT + 1) & M128
    assert xsl_rr((A * s0 + B * inc) & M128) == int(ref[m - 1])
print('jump ok')
