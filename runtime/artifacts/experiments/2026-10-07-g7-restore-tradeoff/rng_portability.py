"""
Does torch.randn on a CUDA device give the same numbers on two different GPUs, and for which tensor sizes? (G7, the question behind arm D)

Reading of PyTorch (ATen/native/cuda/DistributionTemplates.h, calc_execution_policy and the grid-stride kernel): blocks of 256 threads,
grid = min(ceil(numel / 256), multiProcessorCount * (maxThreadsPerMultiProcessor / 256)); thread t draws one Philox subsequence and
writes the elements t, t + T, t + 2T, t + 3T with T = grid * 256 (4 numbers per call). While numel <= T every element is written by the
pass ii = 0 of thread t = element index, whatever the grid is; above T the element -> random number mapping depends on T, that is on the GPU.
T at its largest is 107,520 on the RTX 5070 Ti (420 blocks) and 22,528 on the GTX 1660 SUPER (88 blocks). So a tensor of at most 22,528
elements should give the same numbers on both (inference from the source; the sizes around the limits are tested here). This is a
correction of a first version of this text that put the limit at 90,112.
This script prints a SHA-256 of the bytes for several sizes and for a "chunked" scheme (one generator, consecutive calls of CHUNK elements),
so that the output of two machines can be compared. It only measures the equality of the random numbers, nothing else.

Usage: python rng_portability.py --out FILE
"""
import argparse, hashlib, json, sys, time
from pathlib import Path

import torch

SEED = 123456789
SIZES = [1_000, 4_096, 16_384, 22_528, 22_529, 32_768, 65_536, 90_112, 107_520, 131_072, 430_080, 1_048_576, 4_194_304, 16_777_216]
CHUNKS = [8_192, 16_384, 22_528, 32_768, 65_536]
TOTAL = 4_194_304


def sha(t: torch.Tensor) -> str:
    return hashlib.sha256(t.detach().cpu().contiguous().view(torch.uint8).numpy().tobytes()).hexdigest()[:16]


def one_call(n: int, dtype=torch.float32) -> str:
    gen = torch.Generator(device="cuda")
    gen.manual_seed(SEED)
    return sha(torch.randn((n,), generator=gen, dtype=dtype, device="cuda"))


def chunked(chunk: int, total: int) -> str:
    gen = torch.Generator(device="cuda")
    gen.manual_seed(SEED)
    parts = [torch.randn((min(chunk, total - s),), generator=gen, dtype=torch.float32, device="cuda") for s in range(0, total, chunk)]
    return sha(torch.cat(parts))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", required=True)
    a = p.parse_args()
    out = Path(a.out)
    if out.exists():
        sys.exit(f"refusing to overwrite {out}")
    props = torch.cuda.get_device_properties(0)
    result = {"gpu": props.name, "capability": f"{props.major}.{props.minor}", "sm_count": props.multi_processor_count,
              "max_threads_per_sm": props.max_threads_per_multi_processor, "torch": torch.__version__, "cuda": torch.version.cuda,
              "wave_elements": props.multi_processor_count * (props.max_threads_per_multi_processor // 256) * 256 * 4,
              "one_call_fp32": {n: one_call(n) for n in SIZES}, "one_call_fp16_4M": one_call(TOTAL, torch.float16),
              "chunked_fp32": {c: chunked(c, TOTAL) for c in CHUNKS}}
    # speed of the chunked scheme for the size of the whole model (494,032,768 elements) on this GPU, chunk 65,536
    gen = torch.Generator(device="cuda"); gen.manual_seed(SEED)
    buf = torch.empty((65_536,), dtype=torch.float32, device="cuda")
    torch.cuda.synchronize(); t0 = time.perf_counter()
    calls = 494_032_768 // 65_536
    for _ in range(calls):
        buf.copy_(torch.randn((65_536,), generator=gen, dtype=torch.float32, device="cuda"))
    torch.cuda.synchronize()
    result["chunked_65536_whole_model_seconds"] = time.perf_counter() - t0
    result["chunked_65536_calls"] = calls
    gen = torch.Generator(device="cuda"); gen.manual_seed(SEED)
    buf16 = torch.empty((16_384,), dtype=torch.float32, device="cuda")
    torch.cuda.synchronize(); t0 = time.perf_counter()
    calls16 = 494_032_768 // 16_384
    for _ in range(calls16):
        buf16.copy_(torch.randn((16_384,), generator=gen, dtype=torch.float32, device="cuda"))
    torch.cuda.synchronize()
    result["chunked_16384_whole_model_seconds"] = time.perf_counter() - t0
    result["chunked_16384_calls"] = calls16
    out.write_text(json.dumps(result, indent=1) + "\n")
    print(json.dumps(result, indent=1))


if __name__ == "__main__":
    main()
