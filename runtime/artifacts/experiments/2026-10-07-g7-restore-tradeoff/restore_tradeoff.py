"""
Trade-off between how a candidate is perturbed and how the model is brought back (G7 experiment).

Three arms, the same model, the same seeds, the same workload (cot_workload, level 3, FP32 forward pass, the default of O8):

  A  canonical CPU noise (the contract engine) + restore from a snapshot, verified bit for bit      <- what the runtime does today
  B  canonical CPU noise + REVERT BY ARITHMETIC: perturb again with -sigma (the noise is generated a second time)
  C  GPU noise of torch.Generator (seed mixed with the tensor name) + revert by arithmetic: add_(noise, alpha=+-sigma) in FP16
     <- the way of es-at-scale and Agentic-ESOpt (not portable between two kinds of GPU, see the cross-GPU evidence)
  D  the same GPU noise as C + restore from the snapshot (added after the first runs: with A, B, C the source of the noise and the way of
     coming back were changed together; A, B, C, D make a 2 x 2 table: noise CPU or GPU, back by snapshot or by arithmetic)

Measured per candidate (CUDA synchronised): perturb, shadow refresh, rollout and restore/revert seconds. After every candidate, OUTSIDE the
timing, the model is compared with the pristine weights: elements that differ, largest absolute difference, relative L2 error. The reward of
the unperturbed model is evaluated before the first candidate and after the last one, so that the effect of the accumulated drift on the
answers can be seen. Arms A and B use the same seeds and the same noise, so their candidate rewards can be compared one by one.

Usage: python restore_tradeoff.py --model-path SNAP --candidates 24 --questions 32 --out FILE
"""
import argparse, hashlib, json, os, statistics, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import torch

import cot_workload as W
from heteroes.es.perturb import perturb_model_
from heteroes.es.snapshot import restore_from_snapshot_, take_snapshot
from heteroes.eval.precision import EvalModel
from heteroes.model.loading import check_noise_selftest, load_pinned_model
from heteroes.model.schema import resolve_tensors
from heteroes.noise.contracts import DEFAULT_CHUNK_ELEMENTS

SIGMA = 1e-3
GPU_CHUNK = 8_388_608          # the chunk of es-at-scale's worker


def sync():
    torch.cuda.synchronize()


def tensor_id(name: str) -> int:
    return int.from_bytes(hashlib.blake2b(name.encode(), digest_size=8).digest(), "little")


@torch.no_grad()
def gpu_perturb_(model, schema, seed: int, sigma: float) -> None:
    """The perturbation of Agentic-ESOpt: per-tensor torch.Generator on the device, noise in FP32, added in the dtype of the tensor with alpha=sigma.
    sigma negative = the revert."""
    for entry, tensor in zip(schema.entries, resolve_tensors(model, schema), strict=True):
        flat = tensor.view(-1)
        gen = torch.Generator(device=tensor.device)
        gen.manual_seed((int(seed) ^ tensor_id(entry.canonical_name)) & 0xFFFFFFFFFFFFFFFF)
        for start in range(0, flat.numel(), GPU_CHUNK):
            end = min(start + GPU_CHUNK, flat.numel())
            noise = torch.randn((end - start,), generator=gen, dtype=torch.float32, device=tensor.device)
            flat[start:end].add_(noise.to(flat.dtype), alpha=float(sigma))


@torch.no_grad()
def drift(model, schema, reference: list[torch.Tensor]) -> dict:
    differ, total, max_abs, sq_diff, sq_ref = 0, 0, 0.0, 0.0, 0.0
    for tensor, ref in zip(resolve_tensors(model, schema), reference, strict=True):
        now = tensor.detach().cpu()
        differ += int((now.view(torch.int16) != ref.view(torch.int16)).sum())
        total += now.numel()
        d = now.float() - ref.float()
        max_abs = max(max_abs, float(d.abs().max()))
        sq_diff += float((d * d).sum())
        sq_ref += float((ref.float() ** 2).sum())
    return {"elements_differing": differ, "fraction_differing": differ / total, "max_abs_diff": max_abs, "relative_l2": (sq_diff / sq_ref) ** 0.5}


def run_arm(arm, loaded, ev, snapshot, reference, qa, seeds, chunk):
    model, schema = loaded.model, loaded.schema

    def perturb(seed):
        if arm in ("C", "D"):
            gpu_perturb_(model, schema, seed, SIGMA)
        else:
            perturb_model_(model, schema, seed, SIGMA, DEFAULT_CHUNK_ELEMENTS)

    def back(seed):
        if arm in ("A", "D"):
            restore_from_snapshot_(model, schema, snapshot)
        elif arm == "B":
            perturb_model_(model, schema, seed, -SIGMA, DEFAULT_CHUNK_ELEMENTS)
        else:
            gpu_perturb_(model, schema, seed, -SIGMA)

    def candidate(seed, timed=True):
        t = {}
        sync(); m = time.perf_counter()
        perturb(seed); sync(); now = time.perf_counter(); t["perturb"], m = now - m, now
        ev.refresh(); sync(); now = time.perf_counter(); t["refresh"], m = now - m, now
        reward = W.evaluate(ev.model, loaded.tokenizer, qa, chunk)
        now = time.perf_counter(); t["rollout"], m = now - m, now
        back(seed); sync(); now = time.perf_counter(); t["back"], m = now - m, now
        t["total"] = t["perturb"] + t["refresh"] + t["rollout"] + t["back"]
        return reward, t

    restore_from_snapshot_(model, schema, snapshot)                 # every arm starts from the pristine weights
    candidate(9999)                                                  # warm-up (kernels, allocator, noise pool), not recorded
    restore_from_snapshot_(model, schema, snapshot)
    torch.cuda.reset_peak_memory_stats()

    ev.refresh(); base0 = W.evaluate(ev.model, loaded.tokenizer, qa, chunk)
    rows = []
    for seed in seeds:
        reward, t = candidate(seed)
        rows.append({"seed": seed, "reward": reward["mean_reward"], "rewards": reward["rewards"], "timing": t, "drift": drift(model, schema, reference)})
        print(arm, seed, {k: round(v, 3) for k, v in t.items()}, "reward", reward["mean_reward"], "differ", rows[-1]["drift"]["elements_differing"], flush=True)
    ev.refresh(); base1 = W.evaluate(ev.model, loaded.tokenizer, qa, chunk)
    peak = torch.cuda.max_memory_allocated()
    final_drift = drift(model, schema, reference)
    restore_from_snapshot_(model, schema, snapshot)
    med = lambda key: statistics.median(r["timing"][key] for r in rows)
    return {"arm": arm, "candidates": rows, "median_seconds": {k: med(k) for k in ("perturb", "refresh", "rollout", "back", "total")},
            "base_reward_before": base0["mean_reward"], "base_reward_after": base1["mean_reward"],
            "base_answers_changed": sum(a != b for a, b in zip(base0["texts"], base1["texts"])),
            "final_drift": final_drift, "peak_gpu_bytes": peak}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model-path", required=True)
    p.add_argument("--candidates", type=int, default=24)
    p.add_argument("--questions", type=int, default=32)
    p.add_argument("--level", type=int, default=3)
    p.add_argument("--chunk", type=int, default=16)
    p.add_argument("--arms", default="A,B,C,D")
    p.add_argument("--out", required=True)
    a = p.parse_args()
    out = Path(a.out)
    if out.exists():
        sys.exit(f"refusing to overwrite {out}")
    check_noise_selftest()
    loaded = load_pinned_model(a.model_path, "cuda")
    ev = EvalModel(loaded.model, "float32")
    qa = W.make_questions(a.questions, a.level)
    snapshot = take_snapshot(loaded.model, loaded.schema)
    reference = [t.detach().cpu().clone() for t in resolve_tensors(loaded.model, loaded.schema)]
    seeds = list(range(a.candidates))
    result = {"gpu": torch.cuda.get_device_name(), "torch": torch.__version__, "noise_threads": os.environ.get("HETEROES_NOISE_THREADS"),
              "cpu_count": os.cpu_count(), "sigma": SIGMA, "candidates": a.candidates, "questions": a.questions, "level": a.level, "chunk": a.chunk,
              "snapshot_host_bytes": sum(t.numel() * t.element_size() for t in reference), "arms": {}}
    for arm in a.arms.split(","):
        result["arms"][arm] = run_arm(arm, loaded, ev, snapshot, reference, qa, seeds, a.chunk)
        out.write_text(json.dumps(result, indent=1) + "\n")        # partial results survive a crash of a later arm
    print(json.dumps({k: {"median_seconds": v["median_seconds"], "final_drift": v["final_drift"], "base": (v["base_reward_before"], v["base_reward_after"])}
                      for k, v in result["arms"].items()}, indent=1))


if __name__ == "__main__":
    main()
