"""Engine v2 made on a CUDA device: the same integer law and the SAME BITS as `engine_v2` on the CPU.

This is an execution choice, not another engine: the recipe still names `pcg64_u32_to_f16_normal_quantile_v2`, and a
CPU-only machine (or one where this path is off) makes exactly the same noise. Everything is integer arithmetic, so
the GPU, its driver and compiler cannot change a bit; the self-test below still compares with the CPU engine before
the path is used on a device.

- PCG64 (numpy's `PCG64(seed)`: SeedSequence seeding, 128-bit LCG, XSL-RR output) is evaluated for every 64-bit word
  of a chunk at once by jumping ahead: state_m = A_m * state_0 + B_m * increment (mod 2**128) with A_m = MULT**m and
  B_m = 1 + MULT + ... + MULT**(m-1), tables that do not depend on the seed. The kernel is compiled at run time by
  NVRTC through `torch.cuda.jiterator` (part of every CUDA build of PyTorch, Windows included); 128-bit products are
  made of 64-bit ones with `__umul64hi` because NVRTC has no `__int128` outside Linux.
- The little-endian 32-bit halves of the words are mapped to FP16 bits by the pinned thresholds of `engine_v2`
  (`searchsorted`, right side: the number of thresholds <= u), exactly as on the CPU.

HETEROES_NOISE_DEVICE=cpu turns the path off (the CPU engine is then used everywhere).
"""

import os
import threading

import numpy as np

from heteroes.noise.engine_v2 import _TABLE, derive_chunk_seed

ENV_DEVICE = "HETEROES_NOISE_DEVICE"
PCG_MULTIPLIER = 0x2360ED051FC65DA44385DF649FCCF645
_M64 = (1 << 64) - 1
_M128 = (1 << 128) - 1

_KERNEL = r"""
template <typename T> T pcg64_jump_word(T a_lo, T a_hi, T b_lo, T b_hi, T s_lo, T s_hi, T i_lo, T i_hi) {
  typedef unsigned long long u64;
  u64 al = (u64)a_lo, ah = (u64)a_hi, bl = (u64)b_lo, bh = (u64)b_hi;
  u64 sl = (u64)s_lo, sh = (u64)s_hi, il = (u64)i_lo, ih = (u64)i_hi;
  u64 p_lo = al * sl, p_hi = __umul64hi(al, sl) + al * sh + ah * sl;
  u64 q_lo = bl * il, q_hi = __umul64hi(bl, il) + bl * ih + bh * il;
  u64 lo = p_lo + q_lo, hi = p_hi + q_hi + (lo < p_lo ? 1ull : 0ull);
  u64 x = hi ^ lo;
  unsigned int r = (unsigned int)(hi >> 58);
  return (T)(long long)((x >> r) | (x << ((64u - r) & 63u)));
}
"""

_lock = threading.Lock()
_kernel = None
_tables = {}  # (device, words) -> (a_lo, a_hi, b_lo, b_hi, thresholds)
_verified = {}  # device -> bool


def _signed(values):
    return np.array(values, dtype=np.uint64).view(np.int64)


def jump_tables(words: int) -> np.ndarray:
    """[4, words] int64 bit patterns of A_m (lo, hi) and B_m (lo, hi) for m = 1..words."""
    a, b, rows = 1, 0, np.empty((4, words), dtype=np.uint64)
    for m in range(words):
        a, b = (a * PCG_MULTIPLIER) & _M128, (b * PCG_MULTIPLIER + 1) & _M128
        rows[0, m], rows[1, m], rows[2, m], rows[3, m] = a & _M64, a >> 64, b & _M64, b >> 64
    return rows.view(np.int64)


def chunk_states(addresses) -> np.ndarray:
    """[C, 4] int64 bit patterns of (state lo, state hi, increment lo, increment hi) of numpy's PCG64 per chunk."""
    rows = np.empty((len(addresses), 4), dtype=np.uint64)
    for i, address in enumerate(addresses):
        state = np.random.PCG64(derive_chunk_seed(address)).state["state"]
        rows[i] = (state["state"] & _M64, state["state"] >> 64, state["inc"] & _M64, state["inc"] >> 64)
    return rows.view(np.int64)


def _resources(device, words):
    import torch

    global _kernel
    with _lock:
        if _kernel is None:
            from torch.cuda.jiterator import _create_jit_fn

            _kernel = _create_jit_fn(_KERNEL)
        key = (str(device), words)
        if key not in _tables:
            jump = torch.from_numpy(jump_tables(words)).to(device)
            thresholds = torch.from_numpy(_TABLE.astype(np.int32)).to(device)  # every threshold is below 2**31
            _tables[key] = (*jump.unbind(0), thresholds)
        return _kernel, _tables[key]


def generate_chunks(addresses, lengths, device):
    """FP16 noise of the given chunks, joined in order, as one tensor on `device` (bits equal to engine_v2)."""
    import torch

    if len(addresses) != len(lengths) or not addresses:
        raise ValueError("one length per chunk address is needed")
    for address, n in zip(addresses, lengths):
        if not 1 <= n <= address.chunk_elements:
            raise ValueError("n must be in range 1 <= n <= chunk_elements")
    words = (max(lengths) + 1) // 2
    kernel, (a_lo, a_hi, b_lo, b_hi, thresholds) = _resources(
        device, (max(a.chunk_elements for a in addresses) + 1) // 2
    )
    states = torch.from_numpy(chunk_states(addresses)).to(device)
    raw = kernel(
        a_lo[:words], a_hi[:words], b_lo[:words], b_hi[:words],
        states[:, 0:1], states[:, 1:2], states[:, 2:3], states[:, 3:4],
    )  # fmt: skip
    halves = raw.view(torch.int32)  # little-endian: word 2k is the low half of 64-bit word k, as numpy's view("<u4")
    magnitude = torch.searchsorted(thresholds, halves & 0x7FFFFFFF, right=True, out_int32=True)
    bits = (magnitude | (((halves >> 31) & 1) << 15)).to(torch.int16).view(torch.float16)
    if all(n == bits.shape[1] for n in lengths):
        return bits.reshape(-1)
    return torch.cat([bits[i, :n] for i, n in enumerate(lengths)])


def selftest(device) -> bool:
    """Bits equal to the CPU engine for fixed chunks, a full one, an odd tail and a small chunk size."""
    from heteroes.noise.contracts import ChunkNoiseAddress
    from heteroes.noise.engine_v2 import generate_chunk_noise

    cases = [
        (ChunkNoiseAddress(7, "selftest-v2-cuda", 0, 0, 2**18), 2**18),
        (ChunkNoiseAddress(2**62 + 11, "selftest-v2-cuda", 291, 37, 2**18), 2**18 - 1),
        (ChunkNoiseAddress(5, "selftest-v2-cuda", 3, 2, 1000), 7),
    ]
    for address, n in cases:
        expected = generate_chunk_noise(address, n).view(np.uint16)
        made = generate_chunks([address], [n], device).cpu().numpy().view(np.uint16)
        if not np.array_equal(made, expected):
            return False
    return True


def enabled(device) -> bool:
    """True when the noise of tensors on `device` can be made there: a CUDA device whose self-test passed."""
    if getattr(device, "type", None) != "cuda" or os.environ.get(ENV_DEVICE, "").lower() == "cpu":
        return False
    key = str(device)
    if key not in _verified:
        try:
            _verified[key] = selftest(device)
        except Exception:  # no NVRTC, a driver without jiterator support: the CPU engine makes the same bits
            _verified[key] = False
    return _verified[key]
