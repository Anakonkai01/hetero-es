"""Cross-GPU check for HeteroES (self-contained: needs only torch, numpy, transformers).

Run it on any machine with a CUDA GPU (a local box, Colab, Kaggle) and paste the output.
Edit the settings block below, nothing else.

What it does
  1. Prints the environment (GPU, compute capability, torch, CUDA, numpy, python).
  2. Re-implements the noise engine (copy of src/heteroes/noise) and checks it against the
     recorded golden vectors, so a wrong copy or a different NumPy is detected.
  3. Loads Qwen2.5-0.5B-Instruct at the pinned revision, checks the parameter layout and the
     schema hashes (probe format and production format).
  4. Optionally regenerates ALL noise with the probe schema hash and compares the global hash
     recorded by the 2026-09-29 probe on the 5070 Ti and the 1660S.
  5. Perturbs all 494,032,768 weights with several compute methods (GPU, CPU, fused and unfused)
     and compares them bit by bit. Methods with the same whole-model hash are bit-identical.

It writes nothing to disk except what the Hugging Face cache needs.
"""
import hashlib
import itertools
import json
import os
import platform
import sys
import time

import numpy as np
import torch

# ----------------------------- settings (edit here) -------------------------------------
SIGMA = 1e-3                       # rounded to float32 below
MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"
REVISION = "7ae557604adf67be50417f59c2c2f167def9a775"
MODEL_PATH = os.environ.get("MODEL_PATH") or None   # local copy; None = download MODEL_ID@REVISION
CHECK_NOISE = True                 # step 4 (slow on a weak CPU: about 10-60 s)
QUICK = os.environ.get("QUICK") == "1"   # only the first 20 tensors (smoke test, hashes not comparable)
SLAB = 1 << 25                     # elements per slab; bounds memory. Must be a multiple of C
# -----------------------------------------------------------------------------------------

C = 262_144
ENGINE_VERSION = "numpy_pcg64_normal_f32_to_f16_v1"
SCHEMA_VERSION = "heteroes.parameter_schema.v1"
PROBE_SCHEMA_HASH = "152e9d82e61d6610a414466026ac60a13e718924dfdf0416809686adcf4188e1"
PRODUCTION_SCHEMA_HASH = "0b21250e331398a266785dc473da3a8b8f5e8f98fa15e9044637d742eb7845ec"
PROBE_GLOBAL_NOISE_HASH = "816c15300c45ca9e85468b7787bc4ce313a87d1e74e6429e48eb9e6d357dafda"
# (param, chunk, n, sha256 of the float16 bytes), candidate_seed = 0
GOLDEN_PROBE = [
    (0, 0, 262144, "1c7a5a141fb785001881807b2bf0c9f81a1f2acf61877b1d2b2e4d029cfb8a35"),
    (0, 519, 81920, "8f57f603def436e1a642e71988b80a39331efaf9273e32634fe9f305f48ec405"),
    (1, 0, 262144, "34cc1872a32730731bb5b753277885281dd31aa0c27fdfbdcdd09c001a23eda8"),
    (2, 0, 896, "56d3f8f512beadbebf9cbf0b1e6fda5143f7940375fc4af99a3437943af12602"),
    (289, 0, 896, "3ed137fd746d5f0655e81731e39e80df6857404c5644dad5dd40b6a6767a25ae"),
]
GOLDEN_PRODUCTION = [   # regression guard produced by the engine on the 5070 Ti host, 2026-10-03
    (0, 0, 262144, "ebe2addd4ba90dfaebfad1582712b1660bd271f99e637c0e554caacf5fbcf87c"),
    (0, 519, 81920, "0d1468c0d034367ccd85e3ac80b5d94d7bf37aaf3a11edb718a35cfc5195466c"),
    (1, 0, 262144, "cd47f0154a3e8a8f2092469da29261479d115bc7db4a7794c8d59518f9a77186"),
    (2, 0, 896, "391a1e33d57bfe7283b4783df050ea51a751a0b61fb9d9050f5941fb40326c3f"),
    (289, 0, 896, "d87d01f6c48aebc7222f9bc18d1cee5981765f37363589140744b69ef6944653"),
]
assert SLAB % C == 0

result = {"checks": {}, "methods": {}}


def sha(b):
    return hashlib.sha256(b).hexdigest()


# ------------------------------- 1. environment ---------------------------------------
assert torch.cuda.is_available(), "No CUDA GPU: switch the runtime to a GPU first."
cap = torch.cuda.get_device_capability(0)
env = {
    "gpu": torch.cuda.get_device_name(0), "compute_capability": f"{cap[0]}.{cap[1]}",
    "torch": torch.__version__, "cuda": torch.version.cuda, "numpy": np.__version__,
    "python": platform.python_version(), "machine": platform.machine(),
    "sigma_float32": float(np.float32(SIGMA)),
}
try:
    import transformers
    env["transformers"] = transformers.__version__
except Exception:
    pass
result["env"] = env
print("=== 1. ENVIRONMENT")
for k, v in env.items():
    print(f"  {k:<18}: {v}")


# ------------------------------- 2. engine copy + golden -------------------------------
def derive_chunk_seed(seed, schema_hash, param, chunk, chunk_elements):
    text = (f"{ENGINE_VERSION}|candidate_seed={seed}|schema={schema_hash}|param={param}"
            f"|chunk={chunk}|chunk_elements={chunk_elements}")
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:16], "little")


def generate_chunk(seed, schema_hash, param, chunk, n):
    rng = np.random.Generator(np.random.PCG64(derive_chunk_seed(seed, schema_hash, param, chunk, C)))
    return rng.standard_normal(n, dtype=np.float32).astype(np.float16)


def num_chunks(numel):
    return -(-numel // C)


def chunk_length(numel, j):
    return min(C, numel - j * C)


def generate_parameter_noise(seed, schema_hash, param, numel):
    out = np.empty(numel, dtype=np.float16)
    for j in range(num_chunks(numel)):
        n = chunk_length(numel, j)
        out[j * C: j * C + n] = generate_chunk(seed, schema_hash, param, j, n)
    return out


print("\n=== 2. NOISE ENGINE (copy) vs recorded golden vectors")
for label, table, schema_hash in (("probe     ", GOLDEN_PROBE, PROBE_SCHEMA_HASH),
                                  ("production", GOLDEN_PRODUCTION, PRODUCTION_SCHEMA_HASH)):
    ok = all(sha(generate_chunk(0, schema_hash, p, c, n).tobytes()) == d for p, c, n, d in table)
    result["checks"][f"golden_{label.strip()}"] = ok
    print(f"  golden {label}: {'PASS' if ok else 'FAIL'}  ({len(table)} chunks)")

# ------------------------------- 3. model + schema -------------------------------------
from transformers import AutoModelForCausalLM  # noqa: E402

print("\n=== 3. MODEL LAYOUT")
kw = dict(revision=REVISION) if MODEL_PATH is None else {}
src = MODEL_PATH or MODEL_ID
try:
    model = AutoModelForCausalLM.from_pretrained(src, dtype=torch.float16, **kw)
except TypeError:
    model = AutoModelForCausalLM.from_pretrained(src, torch_dtype=torch.float16, **kw)
params = list(model.named_parameters())                      # default: duplicates removed
by_id = {}
for name, p in model.named_parameters(remove_duplicate=False):
    by_id.setdefault(id(p), []).append(name)
alias_of = {}
for names in by_id.values():
    if len(names) > 1:
        first = next(n for n, _ in params if n in names)
        alias_of[first] = sorted(set(names) - {first})

entries = []
for i, (name, p) in enumerate(params):
    entries.append({"index": i, "canonical_name": name, "aliases": alias_of.get(name, []),
                    "shape": list(p.shape), "dtype": str(p.dtype), "numel": p.numel()})


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


probe_hash = sha(canonical([{"index": e["index"], "name": e["canonical_name"], "shape": e["shape"],
                              "dtype": e["dtype"], "numel": e["numel"]} for e in entries]))
prod_hash = sha(canonical({"schema_version": SCHEMA_VERSION, "entries": entries}))
total = sum(e["numel"] for e in entries)
checks = {
    "tensors_290": len(entries) == 290, "elements_494032768": total == 494_032_768,
    "alias_group": {k: v for k, v in alias_of.items()} == {"model.embed_tokens.weight": ["lm_head.weight"]},
    "probe_schema_hash": probe_hash == PROBE_SCHEMA_HASH,
    "production_schema_hash": prod_hash == PRODUCTION_SCHEMA_HASH,
}
result["checks"].update(checks)
print(f"  tensors={len(entries)} elements={total:,} aliases={alias_of}")
for k, v in checks.items():
    print(f"  {k:<24}: {'PASS' if v else 'FAIL'}")
if not all(checks.values()):
    print("  !! layout differs from the reference: later hashes are NOT comparable")
if QUICK:
    entries = entries[:20]
    params = params[:20]

# ------------------------------- 4. full noise check -----------------------------------
if CHECK_NOISE and not QUICK:
    print("\n=== 4. FULL-MODEL NOISE vs probe global hash (2105 chunks)")
    t0 = time.time()
    glob = hashlib.sha256()
    for e in entries:
        agg = hashlib.sha256()
        for j in range(num_chunks(e["numel"])):
            agg.update(str(j).encode("ascii"))
            agg.update(generate_chunk(0, PROBE_SCHEMA_HASH, e["index"], j, chunk_length(e["numel"], j)).tobytes())
        glob.update(e["canonical_name"].encode("utf-8"))
        glob.update(agg.hexdigest().encode("ascii"))
    ok = glob.hexdigest() == PROBE_GLOBAL_NOISE_HASH
    result["checks"]["noise_global_hash_matches_probe"] = ok
    print(f"  {glob.hexdigest()[:16]}…  vs probe {PROBE_GLOBAL_NOISE_HASH[:16]}…  -> {'PASS' if ok else 'FAIL'}  ({time.time()-t0:.0f}s)")

# ------------------------------- 5. perturbation study ---------------------------------
sig = float(np.float32(SIGMA))
sig32 = np.float32(SIGMA)
f16, f32, f64 = np.float16, np.float32, np.float64
DESC = {
    "A": "gpu fp16 add_(eps, alpha=sigma)",
    "A2": "gpu fp16 add_ (second run)",
    "B": "gpu fp32: mul, then add, then half   <- proposed (c)",
    "B2": "gpu fp32 mul+add (second run)",
    "C": "gpu torch.add(fp32, alpha) then half",
    "E": "gpu all steps in fp16 (t + e*sigma)",
    "K": "gpu add_ per 262144-chunk",
    "L": "gpu fp32 mul+add per chunk",
    "F": "numpy fp32 mul, then add, then half",
    "G": "torch-cpu fp32 mul, then add, then half",
    "H": "torch-cpu fp16 add_(alpha)",
    "I": "numpy emulated FMA (f64 -> f32 -> f16)",
    "J": "numpy exact f64 -> f16 (single rounding)",
}
bits = lambda t: t.view(torch.int16)


def methods(theta_cpu, eps_cpu):
    t_np, e_np = theta_cpu.numpy(), eps_cpu.numpy()
    t, e = theta_cpu.cuda(), eps_cpu.cuda()
    out = {}

    def gpu_a():
        r = t.clone()
        r.add_(e, alpha=sig)
        return r

    def gpu_b():
        p = e.float() * sig
        return (t.float() + p).half()

    out["A"], out["A2"] = bits(gpu_a()), bits(gpu_a())
    out["B"], out["B2"] = bits(gpu_b()), bits(gpu_b())
    out["C"] = bits(torch.add(t.float(), e.float(), alpha=sig).half())
    out["E"] = bits(t + e * sig)
    ka, kb = t.clone(), torch.empty_like(t)
    for s in range(0, t.numel(), C):
        sl = slice(s, s + C)
        ka[sl].add_(e[sl], alpha=sig)
        kb[sl] = (t[sl].float() + e[sl].float() * sig).half()
    out["K"], out["L"] = bits(ka), bits(kb)
    out["F"] = torch.from_numpy((t_np.astype(f32) + sig32 * e_np.astype(f32)).astype(f16).view(np.int16)).cuda()
    out["G"] = bits((theta_cpu.float() + eps_cpu.float() * sig).half()).cuda()
    h = theta_cpu.clone()
    h.add_(eps_cpu, alpha=sig)
    out["H"] = bits(h).cuda()
    exact = t_np.astype(f64) + f64(sig32) * e_np.astype(f64)
    out["I"] = torch.from_numpy(exact.astype(f32).astype(f16).view(np.int16)).cuda()
    out["J"] = torch.from_numpy(exact.astype(f16).view(np.int16)).cuda()
    return out, bits(t)


print("\n=== 5. PERTURBATION  theta' = theta + sigma*eps   (sigma = %r)" % sig)
names = list(DESC)
glob = {k: hashlib.sha256() for k in names}
pair = {p: 0 for p in itertools.combinations(names, 2)}
unchanged = {"all": [0, 0], "1-D": [0, 0]}
ab = {"sign_of_zero_only": 0, "value_diff": 0, "max_ulp": 0}
total_el = 0
t0 = time.time()
for ti, (e, (_, param)) in enumerate(zip(entries, params)):
    theta_all = param.detach().reshape(-1).contiguous()
    eps_all = torch.from_numpy(generate_parameter_noise(0, PRODUCTION_SCHEMA_HASH, e["index"], e["numel"]))
    for s in range(0, e["numel"], SLAB):
        theta, eps = theta_all[s:s + SLAB].contiguous(), eps_all[s:s + SLAB].contiguous()
        outs, tbits = methods(theta, eps)
        for k in names:
            glob[k].update(outs[k].cpu().numpy().tobytes())
        for a, b in pair:
            pair[(a, b)] += int((outs[a] != outs[b]).sum())
        un = int((outs["B"] == tbits).sum())
        unchanged["all"][0] += theta.numel(); unchanged["all"][1] += un
        if len(e["shape"]) == 1:
            unchanged["1-D"][0] += theta.numel(); unchanged["1-D"][1] += un
        a, b = outs["A"], outs["B"]
        m = a != b
        if m.any():
            zero_both = ((a & 0x7FFF) == 0) & ((b & 0x7FFF) == 0)
            ab["sign_of_zero_only"] += int((m & zero_both).sum())
            vd = m & ~zero_both
            ab["value_diff"] += int(vd.sum())
            ss = vd & ((a >> 15) == (b >> 15))
            if ss.any():
                ab["max_ulp"] = max(ab["max_ulp"], int((a[ss].int() - b[ss].int()).abs().max()))
        total_el += theta.numel()
        del outs
    if ti % 50 == 0:
        print(f"  tensor {ti + 1}/{len(entries)}  {time.time() - t0:.0f}s", flush=True)
print(f"  done: {total_el:,} elements in {time.time() - t0:.0f}s")

groups = {}
for k in names:
    groups.setdefault(glob[k].hexdigest(), []).append(k)
print("\n  Methods with the same whole-model hash are bit-identical on every element:")
for gi, (h, ms) in enumerate(groups.items(), 1):
    print(f"   class {gi}  hash {h[:16]}…")
    for m_ in ms:
        print(f"        {m_:<3} {DESC[m_]}")
print("\n  Elements that differ (bitwise), out of {:,}:".format(total_el))
for a, b, label in [("B", "F", "(c) gpu unfused  vs  numpy unfused        "),
                    ("B", "G", "(c) gpu unfused  vs  torch-cpu unfused    "),
                    ("B", "L", "(c) whole tensor vs  per-chunk            "),
                    ("B", "B2", "(c) run 1         vs  run 2               "),
                    ("A", "B", "add_ (fused)      vs  (c) unfused         "),
                    ("A", "I", "add_ (fused)      vs  emulated FMA        "),
                    ("A", "H", "gpu add_          vs  cpu add_            "),
                    ("B", "E", "(c)               vs  all-fp16 steps      "),
                    ("B", "J", "(c)               vs  exact single rounding")]:
    print(f"   {label}: {pair[(a, b)] if (a, b) in pair else pair[(b, a)]:>12,}")
print("\n  add_ vs (c): sign-of-zero-only = %d, real value differences = %d, max = %d ULP"
      % (ab["sign_of_zero_only"], ab["value_diff"], ab["max_ulp"]))
for k, (tot, un) in unchanged.items():
    print(f"  elements left unchanged by the perturbation ({k}): {un:,}/{tot:,} = {100 * un / max(tot, 1):.2f}%")

result["methods"] = {h[:16]: ms for h, ms in groups.items()}
result["class_of"] = {m_: h[:16] for h, ms in groups.items() for m_ in ms}
result["diffs"] = {f"{a}-{b}": v for (a, b), v in pair.items() if (a, b) in
                   {("B", "F"), ("B", "G"), ("B", "L"), ("B", "B2"), ("A", "B"), ("A", "H"), ("B", "E"), ("A", "I")}}
result["ab"] = ab
result["quick"] = QUICK
print("\n=== RESULT_JSON (paste this line too)")
print(json.dumps(result, sort_keys=True))