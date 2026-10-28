# Separate FP32 + selective CPU-reference decoder — implementation acceptance

Owner explicitly approved implementing a separate decoder and further validation after the one-candidate
[CPU margin probe](../2026-10-20-fp32-margin-cpu-probe/RESULTS.md). New identity:
`hf_fp32_cpu_guard_v1`, opt-in Recipe v3, dataset workloads, FP32 primary evaluation, greedy only.
Historical decoder vocabulary/recipe identities remain unchanged; no frozen noise/update/ledger code changes.

Predeclared hardware check: use the SHA256-verified reconstructed g10 parent and exact candidate seed/sign/
dataset batch from the failing audit, with the new decoder explicitly bound into a new recipe identity.
Run twice on 5070 Ti and Quang, check restored parent, primary weights/input hashes, complete token arrays
and text hashes. Do not substitute this probe for the fresh candidate packages and 50-generation acceptance.

Tests first, scratch mutation checks, then complete CPU checks. Resource failures and unsupported settings
must stop rather than select an unchecked token or submit zero reward. Installed runtimes/live lab unchanged.

## What this does NOT show

This declaration is not a test result, universal numerical error bound or release acceptance. The 0.01 gate
is empirical and can itself disagree at a boundary. Selective CPU FP64 does not prove all architectures
bit-identical. General large-model cost, Windows hardware acceptance, outage/retry and full parity remain.
