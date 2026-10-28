# Reproduced audit mismatch: FP32 inference changes the greedy winner across GPUs

Both machines independently reconstructed all ten original update records from the pinned base model.
Every intermediate child SHA256 matched the original ledger, including the generation-10 parent.
On the exact g10/c5 descriptor, both repeat runs on each GPU were stable:

| Device | Reconstructed completion SHA256 |
|---|---|
| 5070 Ti | 519e5172210e0b97dfc20a761c97caa4635056912d67f6120afb52213fca8471 |
| Quang WSL RTX 3060 | 42c3204f4d1ed47de9bf73e463ec5333b3587763134e478b65ae9d55ac589dab |

Inputs, attention masks, perturbed FP16 weight SHA256 and widened FP32 evaluation weight SHA256
all match bit for bit. The greedy text differs only in row 0, starting at generated token index 13:
5070 selects token 16861; Quang selects token 4995. The first thirteen tokens are identical.
Both use highest matmul precision, TF32 matmul disabled, SDPA, same pinned software versions.
This reproduces the audit's exact two hashes offline, with no coordinator/audit traffic.
It localizes this failure to inference arithmetic/decoding rather than differing weights or input rows.
It does not prove there are no separate audit or lifecycle bugs elsewhere.

## Backend and precision probes

Top two processed scores at the first divergence, each from the same prefix:

| Mode | 5070 Ti (winner, score gap) | Quang 3060 (winner, score gap) | Entire text arrays equal? |
|---|---|---|---|
| SDPA FP32 | 16861, 0.0002918243 | 4995, 0.0004539490 | no |
| eager FP32 | 4995, 0.0010871887 | 4995, 0.0006980896 | yes |
| forced math SDPA FP32 | 16861, 0.0002918243 | 4995, 0.0004539490 | no |
| model.double() only | 16861, 0.0000019073 | 4995, 0.0000019073 | no |
| full reference FP64 forward | 16861 | 16861 | yes |

Changing to eager aligns this one case but does not eliminate FP32 rounding differences, so it is not
claimed as a general correctness fix. Merely casting the model to FP64 also fails: the model explicitly
casts normalization/rotary/other intermediates to FP32. The full-reference prototype preserves FP64
inside forward calls (redirects explicit FP32 conversion operations there), while the existing HF
generation loop still rounds returned logits to FP32 and applies its normal processors/greedy argmax.
The generation's output score pairs then match on both devices: 25.17686653137207 and 25.17683219909668.
Its text hash equals the original 5070 result. No noise/update/ledger code or reward tolerance changed.

Single instrumented full-reference generation (8 rows x up to 32 tokens): 2.1917 s on 5070 Ti,
7.3990 s on Quang. This is a diagnostic observation, not a throughput benchmark or a release cost estimate.

## Operator setup correction

The first Quang probe incorrectly set only /usr/lib/wsl/lib, bypassing the packaged Worker's
worker_environment() helper. The process segfaulted in a stale Linux PTX JIT library
libnvidia-ptxjitcompiler.so.580.178.04, before any reconstructed generation completed.
The probe was relaunched through the existing helper, which selects the matching Windows driver
libraries. Both successful Quang receipts use that helper. No host driver or packaged runtime was modified.
Do not treat this initial probe-launch mistake as the audit mismatch's cause.

## Reproducibility and policy status

`inputs/` has the exact recipe/plan, file-backed dataset/splits, descriptor and ten update records,
without lease credentials. Scripts are preserved exactly as run. `*-baseline.json`, `*-modes.json`,
`*-precise64.json` and comparison receipts retain texts, token IDs, top scores, settings and weight hashes.
The private cached reconstructed parent is under .scratch/r11-audit-investigation/parent-fp16.bin locally
and /tmp/heteroes-audit-investigation/parent-fp16.bin on Quang; neither is committed.

Owner decision requested asynchronously: add a separately identified reference FP64 decoder for new
acceptance/release runs, preserve hf_generate and all previous recipe meanings. The existing plan's
50-generation spec is FP32, and numerical-contract section 17 explicitly leaves near-tie policy to the
owner. The prototype is not silently installed as a behavior fix. Implementation/tests and a fresh
candidate must precede renewed hardware and 50-generation release acceptance if that choice is approved.

## What this does NOT show

Only the exact failing candidate is reproduced. No universal cross-GPU theorem, no 50-generation
acceptance, no learning or speedup claim, no Windows reference-decoder acceptance. No product source,
installed runtime, live lab, installer publication, merge, push or device approval changed in this investigation.
Audit equality remains strict; a new decoder must have its own recipe identity and declared precision.
