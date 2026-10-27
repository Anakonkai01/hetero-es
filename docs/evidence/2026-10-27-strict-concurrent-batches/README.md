# Concurrent strict request partitions, 2026-10-27

Unselected scheduling probe, using unchanged B22 runtime `0eb86cb9`. One FP16 model is shared read-only
by two independent `IntegerDecoderGraph` request owners, each with its own metadata, caches, graph,
persistent host worker and CUDA stream. Partition the same ordered 32 requests into two groups of 16,
then flatten results in the original order. No prompt deduplication, prefix reuse, precision change or
EOS stopping is introduced.

The first full-model attempt failed during simultaneous Torch graph capture. It is retained in
`raw/full-two-01.log` and `harness/concurrent_v1.py`, not treated as a successful run. The revised helper
initializes/captures each owner in isolation when the request shape/token budget/weight binding changes,
then allows concurrent replay. Cold setup is excluded by the same untimed warmup used for the baseline;
timed requests include worker/barrier overhead, duplicate per-request metadata refresh and all GPU work.

## Results and decision

`raw/full-two-02.json`, five samples per variant, synchronized wall time on the local 5070 Ti:

| Case | Batch 32 before | Concurrent 2 × 16 | Batch 32 after |
| --- | ---: | ---: | ---: |
| short32, token/s | 9858.2 | 7199.6 | 9861.4 |
| chat128, token/s | 9852.1 | 7732.0 | 9823.0 |

Every timed and warmup result matches the unchanged batch-32 token sequences. The report verifies that
the model weight storage is shared and records source hashes and peak allocated memory. This finite probe
does not attribute the slowdown separately to bandwidth, smaller GEMMs, host contention or scheduling.

The final helper's fixture regression (`raw/tests-02.log`) compares ordered results with the independent
CPU B22 decoder across parent, changed live weights and exact restore. The earlier helper's passing fixture
receipt is retained separately; it did not expose the full-model capture failure.

**Reject this schedule.** The approximately 27% / 21% throughput losses do not justify trying more
partitions without new evidence. The selected runtime and request scheduling remain unchanged.

## What this does NOT show

No faster decoder, portable concurrent capture, managed multi-request support, arbitrary concurrent model
mutation, cross-host/native acceptance, quality/learning result or 80%-vLLM result is established. No lab
state, deployment or existing environment was changed. No mutant qualification is claimed for this rejected helper.
