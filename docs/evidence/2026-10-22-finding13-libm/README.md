# Finding 13 diagnosed: the CPU noise engine depends on the system's `log1pf` (glibc 2.39 vs 2.43) (2026-10-22 ~20:30)

Run `4eadb5b4…` (audit run, [../2026-10-22-candidate13c-audit-run/](../2026-10-22-candidate13c-audit-run/README.md)): nhut's
worker replayed the update g7→g8 to `2b9b3f1e…` instead of the coordinator's `d864a9b6…`, then restarted 6 times. All
commands ran on copies of the run documents and ledger (`.scratch/f13`, `~/f13-diag` on nhut); same runtime
`756272d28ef3` (lock `d417ad4a…`) on both machines: Python 3.12.15, numpy 2.5.3, torch 2.13.0+cu132.

| | 5070ti-nhan (coordinator) | 5070ti-nhut |
|---|---|---|
| OS / glibc | Ubuntu 26.04.1 / **2.43** | Ubuntu 24.04.4 / **2.39** |
| CPU | i7-14700KF | Core Ultra 7 265KF |
| GPU driver | 595.91.07 | 580.173.02 |

## Steps and results

1. **Ledger replay** on nhan (`../2026-10-22-candidate13/verify_managed_run.py … --regenerate none`,
   `ledger-replay-nhan.json`): all 10 child hashes equal the ledger. The coordinator's chain is self-consistent.
2. **Same update on both machines** (`diag_update.py`, outside the worker, generation 7): nhan gives `d864a9b6…`, nhut
   gives `2b9b3f1e…` again (deterministic). Seeds, coefficients and all 290 parent tensors equal; child tensors differ
   in ONE tensor, 118 `model.layers.9.mlp.down_proj.weight`. Per-(tensor, seed) hashes of the fp16 noise differ in two
   places: (118, seed index 8) and (284 `layers.23.mlp.gate_proj`, seed index 10). The second does not change the weights.
3. **Per chunk** (`diag_noise.py`, CPU only, 3 repeats each, identical within a machine): the float32 noise differs in
   one element of several chunks (9 of 34 chunks checked); the fp16 noise only in two of them
   (`differing-elements.json`). Every differing element is a ziggurat TAIL sample (|x| ≥ 3.95 > r = 3.654), where
   numpy's float32 normal calls `log1pf`. The difference is 1 ulp in float32. It changes the fp16 value only when the
   float32 value lies on an fp16 rounding boundary: `-4.349609` → fp16 `-4.348` on nhan but `-4.35` on nhut.
4. **libm probe** (`libm_probe.py`, 300,000 fixed inputs through `ctypes` into `libm.so.6`): `log1pf` differs in
   21,846 (7.3 %) by at most 1 ulp; `expf` and `logf` equal. glibc 2.41+ ships correctly rounded (CORE-MATH) `log1pf`;
   numpy's wheels link the system `libm.so.6`, so the runtime does not pin it.

## Cause

The engine `numpy_pcg64_normal_f32_to_f16_v1` is a function of numpy **and of the host libm** (`log1pf` in the
ziggurat tail, also the rejection test there). The noise self-test (`noise/selftest.py`, 5 golden chunks) passes on
both machines because its chunks contain no sensitive tail sample. A different noise element changes a weight only when
the update lands on an fp16 boundary. That makes the mismatch rare: generations 0-6 replayed fine, and earlier
multi-machine parity runs passed.

Second defect (the 6 restarts): after `ReplayFailed` the worker falls back to a full synchronization. A public-only
worker cannot do that (`bulk_unavailable` → exit `needs_private_route`, nhut's `events.jsonl`). The agent restarts it,
the new process replays from the base weights and fails at the same record, and so on.

## What this does NOT show

- Which side is "right": the contract never named a libm. glibc ≥ 2.41's `log1pf` is correctly rounded, so it has one
  answer; older glibc, Windows' UCRT and macOS' libm are not, and they were not probed here.
- How often candidate evaluations differ: a worker on glibc 2.39 perturbs with the same rare noise differences, so its
  perturbed weights can differ from the canonical ones in a few elements. The audits of this run matched (8/8), but
  that shows nothing about the general rate.
- Whether the 3060 WSL workers or the Windows app have the same libm as nhan (machines offline / not probed).
- Nothing was changed in `runtime/src/heteroes/{noise,es,ledger}`, the worker, the lab or either machine's state.
