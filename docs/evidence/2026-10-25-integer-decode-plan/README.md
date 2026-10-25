# Bounded automatic integer decode planning — 2026-10-25

The preceding trained prototype roughly doubled B8/B32 throughput on two models with exact final-logit/token
equality. This continuation selects a dimension/SM-based integer schedule only inside decode, with an explicit
partial-workspace cap and a conservative admission bound over every possible active batch. Arithmetic is unchanged.

## What this does NOT show

No managed strict/default activation, general quality claim, universal hardware/OS acceptance, near-vLLM completion
or completion of M0–M6. Prototype timings, selected-source tests and lifecycle acceptance remain separate. No push,
merge, deployment, device-state change or learning run. Earlier receipts/counterexamples remain immutable.
