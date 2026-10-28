# Any machine can compute the coordinator's update with the same bits (2026-10-20)

The coordinator's numerical job is the ES update (sum of `z_i * eps_i` in FP32, divided by N, scaled by alpha, one FP16
cast). Two receipts show which machines compute it with the same bits as the 5070 Ti GPU coordinator of the two-machine
run `6590307f…` (4 generations with momentum: 16, 32, 48 and 64 seeds).

1. **Native Windows, RTX 3060 (Thao), already recorded.** During that run the Windows Worker
   (`desktop-6d6e5328c3d1`) replayed every generation's update itself before working on the next one and checked the
   hash (`replay` events, `verified: true`, `unverified_coefficients: 0`; exported from the isolated lab's
   `monitoring_events` into `windows-replays.json`): `c9118c8a→243c00d7`, `243c00d7→1c1e4e7a`, `1c1e4e7a→8c360b4f`, equal
   to the coordinator's child weights.
2. **CPU only (this machine, GPUs hidden).** `cpu_replay.py` recomputes the run's updates on the CPU.
   `cpu-replay-before-fix.json`: generations 0 and 1 equal, generation 2 (48 seeds) different. Cause, measured: PyTorch
   on CUDA divides by a scalar by multiplying with the float32 reciprocal, the CPU divides exactly; the two differ when N
   is not a power of two. With the owner's approval (2026-10-20) `es/update.py` now multiplies by `fp32(1)/fp32(N)`
   (numerical contract section 8). `cpu-replay-5070ti-box.json`: all 4 generations equal, about 0.8 s per seed on the
   CPU. GPU results are unchanged: `tests/es/test_update.py` checks CPU = GPU = NumPy oracle for 3, 4 and 6 seeds on a
   200,000-element tensor; the full runtime suite (2416 passed) needed no golden change.

Mutation (`mutation.txt`): returning to true division is killed. Computing the reciprocal in float64 survives and is an
equivalent mutant: `float32(1/N)` and `fp32(1)/fp32(N)` are equal for every N from 1 to 1,000,000 (checked, same file).

## What this does NOT show

- Windows computed the update on its GPU; a Windows machine without a GPU was not tested, nor was a CPU other than
  this machine's (Intel, Linux).
- Only the update is covered. A coordinator also generates validation texts for checkpoint selection; those come
  from its own device and can differ between devices (they are recorded, not replayed).
- The momentum and coefficient arithmetic run on the CPU's NumPy on every coordinator and were already shared.
