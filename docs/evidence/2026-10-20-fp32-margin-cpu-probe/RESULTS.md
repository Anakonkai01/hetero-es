# One-candidate selective CPU reference result

Both original FP32 traces have 256 generated token slots. Exactly two top-two score gaps are below 0.01:
row 0, steps 3 and 13 (zero-based). The same-prefix step-13 winner is the original cross-GPU divergence.

The scratch guarded loop uses the existing FP32 model and HF generation on GPU. A custom final logits
processor detects a small processed-score gap. It lazily creates a CPU FP64 reference from the current
perturbed FP16 model, recomputes the affected prefix only, and replaces that row's processed scores.
The CPU reference preserves FP64 inside forward calls; HF rounds returned scores to FP32 and applies its
normal repetition processor. This does not change perturbation, noise, update, restore or audit code.

| Measurement | 5070 Ti machine | Quang RTX 3060 machine |
|---|---:|---:|
| Fixed-prefix CPU reference, two calls combined | 0.398 s | 0.598 s |
| Fixed-prefix reference creation | 0.491 s | 0.886 s |
| Unguarded FP32 generation, first ordered run | 0.714 s | 1.560 s |
| Guarded generation, including lazy reference creation | 1.182 s | 2.331 s |
| Lazy reference creation inside guarded run | 0.511 s | 0.950 s |
| Fallback positions during guarded generation | 2 | 2 |

The complete guarded token arrays AND all eight decoded texts match bit for bit across both machines.
Completion SHA256 is `519e5172210e0b97dfc20a761c97caa4635056912d67f6120afb52213fca8471`, the original
5070 result. Unguarded controls reproduce the original two conflicting hashes again. At step 13 the
CPU scores on both machines are 25.17686653137207 (token 16861) and 25.17683219909668 (token 4995).
Parent restore checks pass. CPU reference uses four threads; all reference parameters are asserted to
be CPU float64. GPU reference FP64 is not used by this follow-up.

The CPU FP64 parameter copy alone is about 3.95 GB (494,032,768 parameters times eight bytes), plus
temporary tensors/copy overhead. This is material on a 16 GB machine and scales with model size;
the 0.5B result is not a general deployment recommendation. A production implementation would need
explicit decoder identity/policy, supported-config validation, fail-closed handling and resource limits.

## What this does NOT show

The 0.01 threshold is an empirical probe choice, not a proven bound. A device could classify a gap
differently near that boundary, or arithmetic error could exceed it. CPU FP64 is also finite precision;
agreement here does not establish a cross-CPU theorem. This is one candidate, one workload and two
machines, with no cold/warm throughput study. No production decoder is implemented or approved.
Release step 5 remains blocked; no fresh long run, merge, publication or deployment occurred.

## Pending owner decision

The owner asked why a consumer-GPU product would use FP64. Full-GPU FP64 was proposed too early and
is not being installed. A new asynchronous question presents the measured FP32-GPU / selective-CPU
alternative versus a requirement to avoid FP64 on CPU as well. No elapsed time is taken as approval.
