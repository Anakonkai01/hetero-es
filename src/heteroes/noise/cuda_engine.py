"""
CUDA noise engine, v1 (G7): the noise of a tensor is made on the GPU by `torch.Generator`, in calls of a FIXED small size.

Why this exists. The canonical engine (`engine.py`) makes the noise on the CPU so that every machine gets the same bytes. That costs
0.7 s per candidate on the 5070 Ti and 3.7 s on the 1660S, and the same again inside the coordinator's update. `torch.randn` on a CUDA device
is fast (the whole model in 0.06 s on the 5070 Ti and 0.4 s on the 1660S, in calls of 22,528 elements) but its result depends on the GPU for a big tensor: the kernel runs `min(ceil(numel / 256), SMs * (maxThreadsPerSM / 256))`
blocks of 256 threads, thread t writes the elements t, t + T, t + 2T, t + 3T with T = blocks * 256, so above T elements the number that an
element receives depends on the number of SMs (ATen/native/cuda/DistributionTemplates.h, `calc_execution_policy`). As long as one call
makes at most T elements, element i is made by thread i whatever the GPU is. So this engine never asks for more than CUDA_CALL_ELEMENTS
elements in one call, and a tensor is made by a SEQUENCE of such calls on one generator.

What is part of the contract (changing any of it changes all the noise):
  * the engine version string, the 63-bit seed of a tensor, derived from (engine version, schema hash, candidate seed, parameter index,
    call size) by SHA-256, like the address of a chunk in `engine.py`;
  * CUDA_CALL_ELEMENTS: the tensor is made by calls of this many elements, the last one shorter;
  * the noise is `torch.randn` in float32 cast to float16 (round to nearest even), the same pipeline as engine v1 (O4).
What is NOT part of it: how many elements are applied to the weights at a time (a piece of any multiple of the call size): the bits do not depend on it.

What it relies on, and how that is checked: that the numbers of curand's normal generator are the same on two GPUs when the thread mapping
is the same (the maths functions of the CUDA library: not guaranteed by anybody), and that PyTorch keeps the mapping above. Both are
checked by `compute_noise_fingerprint` (golden values) and by the guard `check_device`, and both must be checked again when torch
is upgraded. The cross-GPU evidence is in `artifacts/experiments/2026-10-07-g7-restore-tradeoff/`. This engine needs a CUDA device even to reconstruct noise (the coordinator too).
"""
import hashlib

import torch

CUDA_ENGINE_VERSION = "torch_cuda_philox_chunked_f32_to_f16_v1"
# 22,528 = 88 blocks of 256 threads: the largest call that two GPUs with different numbers of SMs (the RTX 5070 Ti and the GTX 1660 SUPER)
# still serve with the same thread mapping, measured in `artifacts/experiments/2026-10-07-g7-restore-tradeoff/rng-*.json`: the numbers
# are equal up to 22,528 elements per call and different from 22,529 on. A bigger call is fewer launches, which is what costs time.
CUDA_CALL_ELEMENTS = 22_528
# the noise is applied to the weights in pieces of this many elements (a multiple of the call size)
PIECE_CALLS = 128
PIECE_ELEMENTS = CUDA_CALL_ELEMENTS * PIECE_CALLS


def check_device(device) -> None:
    """The device must run at least CUDA_CALL_ELEMENTS / 256 blocks of the random kernel, or one call would need more than one pass."""
    device = torch.device(device)
    if device.type != "cuda":
        raise RuntimeError(f"the CUDA noise engine needs a CUDA device, got {device}")
    properties = torch.cuda.get_device_properties(device)
    blocks = properties.multi_processor_count * (properties.max_threads_per_multi_processor // 256)
    if blocks * 256 < CUDA_CALL_ELEMENTS:
        raise RuntimeError(f"{properties.name} runs {blocks} blocks of the random kernel: too few for calls of {CUDA_CALL_ELEMENTS} elements")


def derive_tensor_seed(schema_hash: str, candidate_seed: int, parameter_index: int) -> int:
    """The seed (63 bits, what `torch.Generator.manual_seed` accepts on every version) of the noise of ONE tensor of ONE candidate."""
    if not isinstance(candidate_seed, int) or isinstance(candidate_seed, bool) or candidate_seed < 0:
        raise ValueError(f"candidate_seed must be a non-negative integer, got {candidate_seed!r}")
    if not isinstance(parameter_index, int) or isinstance(parameter_index, bool) or parameter_index < 0:
        raise ValueError(f"parameter_index must be a non-negative integer, got {parameter_index!r}")
    address = (f"{CUDA_ENGINE_VERSION}|candidate_seed={candidate_seed}|schema={schema_hash}|param={parameter_index}"
               f"|call_elements={CUDA_CALL_ELEMENTS}")
    return int.from_bytes(hashlib.sha256(address.encode("utf-8")).digest()[:8], "little") & ((1 << 63) - 1)


class _Scratch:
    """One float32 buffer of PIECE_ELEMENTS per device and the views of one call each, shared by every stream (the pieces handed out are
    converted copies, so the buffer is free again after each `next`). Not thread-safe: one stream at a time per device."""
    _cache: dict = {}

    @classmethod
    def get(cls, device: torch.device) -> "_Scratch":
        key = (device, PIECE_ELEMENTS)
        if key not in cls._cache:
            cls._cache.clear()                                    # another size (tests) or device: the old buffer is not needed
            cls._cache[key] = cls(device)
        return cls._cache[key]

    def __init__(self, device: torch.device):
        self.buffer = torch.empty(PIECE_ELEMENTS, dtype=torch.float32, device=device)
        self.views = [self.buffer[start:start + CUDA_CALL_ELEMENTS] for start in range(0, PIECE_ELEMENTS - CUDA_CALL_ELEMENTS + 1, CUDA_CALL_ELEMENTS)]


class TensorNoise:
    """
    The noise of one tensor, handed out in consecutive pieces. `next(count)` returns the next `count` elements as a float16 tensor on the
    device. `count` must be a multiple of CUDA_CALL_ELEMENTS unless it is what is left of the tensor: the sequence of generator calls is
    then always [CUDA_CALL_ELEMENTS, CUDA_CALL_ELEMENTS, ..., remainder], whatever the pieces are, and that is what makes the bytes independent of the piece size.
    """

    def __init__(self, schema_hash: str, candidate_seed: int, parameter_index: int, numel: int, device):
        if not isinstance(numel, int) or isinstance(numel, bool) or numel < 0:
            raise ValueError(f"numel must be a non-negative integer, got {numel!r}")
        check_device(device)
        self.device = torch.device(device)
        self.numel = numel
        self.done = 0
        self._generator = torch.Generator(device=self.device)
        self._generator.manual_seed(derive_tensor_seed(schema_hash, candidate_seed, parameter_index))

    def next(self, count: int) -> torch.Tensor:
        left = self.numel - self.done
        if not isinstance(count, int) or isinstance(count, bool) or not 1 <= count <= left:
            raise ValueError(f"count must be an integer between 1 and the {left} elements left, got {count!r}")
        if count % CUDA_CALL_ELEMENTS != 0 and count != left:
            raise ValueError(f"count must be a multiple of {CUDA_CALL_ELEMENTS} unless it is the rest of the tensor ({left}), got {count}")
        if count > PIECE_ELEMENTS:
            raise ValueError(f"count must be at most {PIECE_ELEMENTS}, got {count}")
        scratch = _Scratch.get(self.device)
        full, rest = divmod(count, CUDA_CALL_ELEMENTS)
        # `normal_(0, 1)` on a view is what `torch.randn` does after it allocates (same kernel, same bits, checked by hash in bench_calls.py);
        # on the slow CPU of the 1660S the factory call was half of the time
        for view in scratch.views[:full]:
            view.normal_(0.0, 1.0, generator=self._generator)
        if rest:
            scratch.buffer[full * CUDA_CALL_ELEMENTS:full * CUDA_CALL_ELEMENTS + rest].normal_(0.0, 1.0, generator=self._generator)
        self.done += count
        return scratch.buffer[:count].to(torch.float16)


def generate_tensor_noise(schema_hash: str, candidate_seed: int, parameter_index: int, numel: int, device) -> torch.Tensor:
    """The whole noise of a tensor as a float16 tensor (for tests and small tensors; the model operations go piece by piece)."""
    stream = TensorNoise(schema_hash, candidate_seed, parameter_index, numel, device)
    pieces = []
    while stream.done < numel:
        pieces.append(stream.next(min(PIECE_ELEMENTS, numel - stream.done)))
    return torch.cat(pieces) if pieces else torch.empty(0, dtype=torch.float16, device=stream.device)


# Five tensors of the fingerprint: sizes around the call size and one of several pieces. The probe schema hash is a fixed string.
_FINGERPRINT_SCHEMA = "0" * 64
_FINGERPRINT_CASES = ((1, 0, 1), (2, 7, CUDA_CALL_ELEMENTS - 1), (3, 123456789, CUDA_CALL_ELEMENTS), (4, 2**53 - 1, CUDA_CALL_ELEMENTS + 1), (5, 42, 3 * 2**20 + 5))


def compute_noise_fingerprint(device="cuda") -> str:
    """SHA-256 over the noise of the golden tensors, made on `device` (about 0.1 s)."""
    digest = hashlib.sha256()
    for index, seed, numel in _FINGERPRINT_CASES:
        noise = generate_tensor_noise(_FINGERPRINT_SCHEMA, seed, index, numel, device)
        digest.update(noise.cpu().view(torch.int16).numpy().tobytes())
    return digest.hexdigest()


# The fingerprint of this engine, equal on the RTX 5070 Ti (sm_120) and the GTX 1660 SUPER (sm_75), both torch 2.13.0+cu132
# (artifacts/experiments/2026-10-07-g7-restore-tradeoff/cudaengine-*.json). A worker or a coordinator whose GPU makes other numbers must not
# take part: its noise is not the noise of the others.
EXPECTED_CUDA_NOISE_FINGERPRINT = "9492a49ab70efe98e2b710e9a9e927f54be658489eae4b549c0cbf7340b9ffaf"


def check_cuda_noise_selftest(device="cuda") -> None:
    check_device(device)
    actual = compute_noise_fingerprint(device)
    if actual != EXPECTED_CUDA_NOISE_FINGERPRINT:
        raise RuntimeError(f"the CUDA noise self-test failed: this GPU and torch do not make the canonical numbers ({actual[:16]}... instead of {EXPECTED_CUDA_NOISE_FINGERPRINT[:16]}...)")
