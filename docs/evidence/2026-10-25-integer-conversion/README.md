# Exact integer weight conversion — 2026-10-25

Continuation from `0ba3af41`. The preceding scratch variant justified selecting a faster execution of the same
row-scaled integer quantization contract, after adding independent exhaustive coverage as a test. All previous
integer feasibility and trained counterexample receipts remain immutable. No managed recipe/default is activated.

## What this does NOT show

Finite tests do not replace the exact normal-domain argument or establish general model quality. This change
does not make the integer contract equal to the previous FP32 tree, qualify native Windows or managed lifecycle,
close the remaining B32 vLLM gap, or complete M1/M2/full M0–M6. No push, merge, deploy, lab/device change or learning run.
