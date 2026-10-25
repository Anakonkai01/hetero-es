# Integer projection feasibility — 2026-10-25

Continuation from clean `abe40dd9`. This work examines a separately versioned numerical reference, as ADR-012
permits, to address the remaining matrix-compute gap. It does not replace the FP32 tree under its identity.
The full M0–M6 objective remains open. No push, merge, deployment, device-state change or learning run.

## What this does NOT show

- No implemented/qualified integer backend is implied by a design or passing reference test.
- Numerical equality to the new contract is distinct from equality to the previous FP32 tree or model quality.
- A synthetic speedup cannot establish multi-model quality, canonical candidate sensitivity, managed lifecycle,
  native Windows, system acceptance or completion of M0–M6.
- No full FP32 or fully quantized second weight matrix/model may be retained on GPU for a performance result.
