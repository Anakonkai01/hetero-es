# SIMT projection vectorization — 2026-10-25

Scratch-only feasibility check following selected attention source 3fd704a5. Four adjacent K products per lane,
independent bounded int64 accumulators and aligned 64-bit FP16 loads retain the same integer reference.
New tests first pass against the unchanged selected kernel, including offsets, tails and every admitted split.

## What this does NOT show

An operator check or paired timing does not qualify universal model quality, managed/native lifecycle or M0–M6.
No precision reduction, second quantized model, learning, deployment or device-state change is authorized here.
