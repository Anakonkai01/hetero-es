# Segmented grouped integer projection feasibility — 2026-10-25

Source baseline `97f62431`. Inspired by the inspected vLLM merged QKV and gate/up layouts.
One CUDA launch routes whole output-column blocks to separate live weight matrices; shared activation quantization.
No concatenated/full quantized weight copy. Preserve independent row exponents, integer sums and final rounding.

## What this does NOT show

Prototype execution is separately recorded and not selected or qualified. Synthetic correctness does not establish
trained throughput, managed lifecycle, native Windows, general quality or completion of M0–M6. No push/merge/deploy.
