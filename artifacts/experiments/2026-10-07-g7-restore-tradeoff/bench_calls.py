"""How much does one call of the random kernel cost from Python, and can the cost be cut? (G7)
Variants, all making the SAME numbers (checked by hash) for a 4M-element stream in calls of K elements:
  randn_out  torch.randn(size, generator, out=slice)           the first version of the engine
  normal_    prebuilt views, view.normal_(0, 1, generator=g)    randn is empty() + normal_(), so the bits are the same, the factory call is skipped
Then the time for the whole model (494,032,768 elements).  Usage: python bench_calls.py --out FILE"""
import argparse, hashlib, json, sys, time
from pathlib import Path

import torch

K = int(sys.argv[sys.argv.index("--k") + 1]) if "--k" in sys.argv else 22_528
SEED = 123456789
WHOLE = 494_032_768


def sha(t):
    return hashlib.sha256(t.cpu().contiguous().view(torch.uint8).numpy().tobytes()).hexdigest()[:16]


def stream_randn_out(total, buf):
    g = torch.Generator(device="cuda"); g.manual_seed(SEED)
    for o in range(0, total, K):
        n = min(K, total - o)
        torch.randn((n,), generator=g, dtype=torch.float32, device="cuda", out=buf[o:o + n])


def make_views(total, buf):
    return [buf[o:o + min(K, total - o)] for o in range(0, total, K)]


def stream_normal_(views):
    g = torch.Generator(device="cuda"); g.manual_seed(SEED)
    for v in views:
        v.normal_(0.0, 1.0, generator=g)


def timeit(fn):
    torch.cuda.synchronize(); t = time.perf_counter(); fn(); torch.cuda.synchronize()
    return time.perf_counter() - t


def main():
    p = argparse.ArgumentParser(); p.add_argument("--out", required=True); p.add_argument("--k", type=int, default=22_528)
    a = p.parse_args()
    out = Path(a.out)
    if out.exists():
        sys.exit(f"refusing to overwrite {out}")
    total = 3 * 2**20 + 5
    b1 = torch.empty(total, device="cuda"); b2 = torch.empty(total, device="cuda")
    stream_randn_out(total, b1); stream_normal_(make_views(total, b2))
    res = {"gpu": torch.cuda.get_device_name(), "k": K, "same_bits": sha(b1) == sha(b2), "hash": sha(b1)}
    big = torch.empty(WHOLE // 8, device="cuda")                     # an eighth of the model, times 8
    res["randn_out_whole_model_s"] = 8 * min(timeit(lambda: stream_randn_out(big.numel(), big)) for _ in range(3))
    views = make_views(big.numel(), big)
    res["normal_whole_model_s"] = 8 * min(timeit(lambda: stream_normal_(views)) for _ in range(3))
    res["calls_whole_model"] = WHOLE // K
    out.write_text(json.dumps(res, indent=1) + "\n"); print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
