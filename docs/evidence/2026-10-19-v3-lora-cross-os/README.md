# v3 LoRA across Linux and native Windows — cause of the adapter difference and a real cross-OS worker run — 2026-10-19

Follows `../2026-10-19-v3-windows` (LoRA comparison failed at `recipeHash`) and handoff
`docs/handoff-v3-audit-recovery.md` section 5 step 1. Source: commit `f4a3a18` on both machines
(Windows copy extracted with `git archive f4a3a18 runtime/src runtime/scripts`, tar SHA-256
`ada79d6d61b5b0c5589ec1bdfd9d2da22ed51a4b4b650317efc276c5d46fcf52`). No source file was changed.

## 1. Why the two seed-7 adapters differ (diagnosis/)

The earlier result is unchanged: Linux `051b79e3…` vs native Windows `7964e412…`. Measured now:

- Both files have the same shape and the same 172,032 non-zero values (the `lora_A` tensors; `lora_B`
  is zero). Only **81** values differ, each by exactly **1 FP16 ULP** (`diagnosis.json`).
- CPU-only probe (`rng_probe.py.txt`) on both machines, Torch 2.13.0+cu132, CPU capability AVX2 on both:
  the raw generator stream after `torch.manual_seed(7)` is **identical** (`random_int64` hash), but
  `torch.empty(4, 896).uniform_(-b, b)` differs (also for float64). `kaiming_uniform_` equals
  `uniform_` on each machine, so PEFT's LoRA initialization inherits the difference.
- Analysis of those 3,584 values (`analyze.py.txt`): 1,904 differ, by at most 1 FP32 ULP of the bound.
  **Every** value is reproduced from one shared 24-bit draw `u` if Linux computes
  `u·2⁻²⁴·(to−from)+from` in double and rounds once, and native Windows computes the same expression
  in float32 with the product and the sum rounded separately.

So the cause is the CPU `uniform_` kernel of the Windows PyTorch build (float32 arithmetic) versus the
Linux build (double accumulation), with the same random draws. It is not the HeteroES noise, restore or
ledger: canonical noise uses NumPy PCG64, and the only torch-CPU random use in `runtime/src` outside
`study/` is `create_initial_adapter`. Consequence: **an adapter seed is not portable across operating
systems; the adapter bytes are.** A Windows coordinator would create different adapters. Whatever
qualification or reference we build must ship and check the canonical adapter file, never regenerate it
from a seed on the device.

The Windows adapter file was copied read-only from the previous run directory; the probe wrote only to the
new private folder `%LOCALAPPDATA%/HeteroES-v3-20261019/diag-lora`. `windows-rng-probe.json` is copied
verbatim from the SSH console output of that probe.

## 2. Native Windows worker consuming the coordinator's adapter (runs/, harness/)

Setup, all with the shipped code paths:

- Coordinator: managed `heteroes.product.runner.main` on this machine's RTX 5070 Ti, listening on its
  Tailscale address. Probe-only change: `harness.py runner` sets the coordinator's `audit_rate` to 1.0
  so every candidate is audited (product default 1/20). LoRA rank 4, alpha 8, q_proj/v_proj; the
  coordinator creates the initial adapter (seed 0) as in a product run.
- Workers: the unchanged CLI `scripts/run_worker.py --run-config … --replay always`. `linux-a` on the
  5070 Ti; `windows-3060` is native Windows CPython 3.12.15 on the RTX 3060 (driver 617.42), using the
  existing pinned interpreter/model read-only, isolated PEFT from the earlier private `deps`, its weight
  cache on the checked D: volume (`Volume{ac23c91d-…}`, new folder `cross-os-lora-cache`). It downloaded
  the initial adapter through the authenticated private weights transport and checked its hash.
- A random shared secret was generated for these runs, passed through a private file, never logged
  (logs were scanned for it), and both copies were deleted afterwards.

Choosing the configuration (all Linux-only, BEFORE any Windows run, each kept in `runs/`):

| Run | Task / sigma / alpha | Result |
| --- | --- | --- |
| linux-baseline | add / 0.001 / 0.001 | PASS, all rewards 1.0, both updates no-op |
| linux-mul | mul / 0.1 / 0.01 | PASS, garbage texts, rewards 0, both no-op |
| linux-mul-s02 | mul / 0.02 / 0.01 | PASS, mixed rewards, generation 0 update **non-no-op** — chosen |

`cross-lora` uses exactly the `linux-mul-s02` configuration except host/port/worker IDs/paths (checked
by diff before the run); `runId`, dataset and model manifest are the same.

Result (`runs/compare-cross-lora.json`, `runs/cross-lora/receipt.json`): **PASS**.

- Same `recipeHash` `06d48520…` and plan, same initial adapter, same 8 candidates, **all 32 texts and
  rewards identical** to the Linux-only run, same child hashes (`01944ed1…` after the non-no-op update).
- `windows-3060` computed 2 candidates and audited the other 6; `linux-a` audited Windows' 2. **8/8
  audits are cross-OS and all match**, no quarantine. Windows replayed the generation-0 update itself
  and verified the child hash (`windows-3060.jsonl`, event `replay`, `verified: true`).
- Every stored reward was re-scored from the texts, and both updates were replayed on a fresh CPU model
  from the transferred adapter (`harness.py verify`).
- Negative controls: comparing against `linux-mul` fails on recipe/plan/children/candidates; one added
  space in one text fails on `candidates` (`runs/negative-*.json`).

Ledgers, weights and the token are not committed (ledgers hold attempt lease tokens).

## What this does NOT show

- No installer, fresh runtime installation, desktop app, Lab Server, pairing or device enrollment: the
  Windows side reuses an existing pinned interpreter plus an isolated extra-dependency folder.
- No backend/admission change and no qualification_v3/reference work (section 5 steps 2–5 remain).
- One short job (2 generations × 4 candidates, 16 new tokens, one non-no-op update), one Windows GPU,
  one prompt set. Not learning evidence, not a long or loaded run, not 1660S evidence.
- The 100% audit rate is a probe override, not product behaviour.
- The diagnosis identifies the arithmetic difference by reproducing every probed value; it does not
  inspect PyTorch's Windows build flags or source, and it does not cover other torch-CPU distributions.
- A native Windows **coordinator** remains unsupported; adapters it creates would differ.
