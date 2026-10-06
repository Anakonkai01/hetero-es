"""
Two measurements behind the decision "the coefficients of an update travel with the record" (ADR-002, contract section 13).
Run:  python measure.py > output.txt        (about 20 seconds; fixed seeds; only NumPy and the package)

1. How big is a generation record?
2. Does the way the float64 sums are ordered change the float32 coefficients of the standardization? (rewards k/96 as in
   the learning pilot.) If it does, two machines that each recompute the coefficients would not always get the same bytes.
3. What would a different coefficient (a residue of 1e-16 instead of 0.0) do to an update? NumPy only, 2 million elements:
   NOT the real apply_es_update_ and NOT the real model.
"""
import math
import platform
import random

import numpy as np

from heteroes.es.update import standardize_rewards
from heteroes.generation_record import GenerationRecord
from heteroes.manifest import derive_seed

print(f"python {platform.python_version()}  numpy {np.__version__}  machine {platform.machine()}  system {platform.system()}")

# ---- 1. size of a record ---------------------------------------------------------------------------------------------
random.seed(0)
print("\n1. size of a generation record (rewards k/96, seeds from derive_seed, alpha 1e-3)")
for n in (8, 32, 128):
    rewards = tuple(random.randint(0, 96) / 96 for _ in range(n))
    record = GenerationRecord(
        "learn", 3, "a" * 64, "b" * 64, tuple(derive_seed("learn", 3, i) for i in range(n)), rewards,
        tuple(float(v) for v in standardize_rewards(rewards)), 1e-3)
    print(f"   N = {n:3d}: {len(record.to_json().encode()):5d} bytes   (the FP16 model is {494_032_768 * 2 / 1e9:.2f} GB)")


# ---- 2. fragility of the coefficients --------------------------------------------------------------------------------
def z_in_order(rewards, order):
    r = np.array([rewards[i] for i in order], dtype=np.float64)
    mean, std = r.mean(dtype=np.float64), r.std(ddof=0, dtype=np.float64)
    return ((np.array(rewards) - mean) / (std + 1e-9)).astype(np.float32)


def z_exact(rewards):
    n = len(rewards)
    mean = math.fsum(rewards) / n
    std = math.sqrt(math.fsum((x - mean) ** 2 for x in rewards) / n)
    return np.array([(x - mean) / (std + 1e-9) for x in rewards], dtype=np.float64).astype(np.float32)


print("\n2. float32 coefficients that change with the order of the float64 sums (20,000 random sets of rewards k/96 each)")
random.seed(1)
for n in (8, 16, 64):
    trials = differ_order = differ_exact = residue_only = 0
    for _ in range(20000):
        rewards = [random.randint(0, 96) / 96 for _ in range(n)]
        if len(set(rewards)) == 1:
            continue
        trials += 1
        base = standardize_rewards(rewards)
        order = list(range(n))
        random.shuffle(order)
        other = z_in_order(rewards, order)
        differ_exact += not np.array_equal(base, z_exact(rewards))
        if not np.array_equal(base, other):
            differ_order += 1
            where = np.nonzero(base != other)[0]
            residue_only += all(abs(base[i]) < 1e-9 and abs(other[i]) < 1e-9 for i in where)
    print(f"   N = {n:2d}: {trials} sets; another order of the sums changed the coefficients in {differ_order} "
          f"({differ_order / trials:.2%}); an exactly rounded mean and std in {differ_exact}; "
          f"of the {differ_order} changes, {residue_only} were only a coefficient 0.0 against a residue below 1e-9")

# ---- 3. what a residue does to an update (NumPy only) ----------------------------------------------------------------
rng = np.random.default_rng(0)
eps = rng.standard_normal((8, 2_000_000)).astype(np.float32)
z1 = np.array([1.2, -0.7, 0.0, 0.4, -1.1, 0.0, 0.9, -0.7], dtype=np.float32)
z2 = z1.copy()
z2[2], z2[5] = np.float32(3e-17), np.float32(-4e-17)


def direction(z):
    acc = np.zeros(eps.shape[1], dtype=np.float32)
    for i in range(8):
        acc = acc + eps[i] * np.float32(z[i])
    return acc / np.float32(8)


d1, d2 = direction(z1), direction(z2)
w = rng.standard_normal(eps.shape[1]).astype(np.float16)
n1 = (w.astype(np.float32) + d1 * np.float32(1e-3)).astype(np.float16)
n2 = (w.astype(np.float32) + d2 * np.float32(1e-3)).astype(np.float16)
print("\n3. two coefficient vectors that differ only by residues of about 1e-17 (2,000,000 elements, NumPy only)")
print(f"   FP32 direction elements that differ: {int((d1 != d2).sum())}   FP16 weights that differ after the update: "
      f"{int((n1.view(np.int16) != n2.view(np.int16)).sum())}")
