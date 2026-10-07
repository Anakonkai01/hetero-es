# G6: one machine, the fast GPU only: what the thread pool and several worker processes give (07/10/2026)

Coordinator and workers all on the 5070 Ti (no 1660S, `--host 127.0.0.1`), `heteroes-match` environment, N = 24 candidates, 4 generations, experiment id `g6local`, the code of the branch
`feat/audit-hardening-g6` (`git_commit` in each `coordinator/events.jsonl`). Produced by `scripts/run_benchmark.py` (conditions `B0`, `B0x2`, `B0x3`: one, two, three worker
processes on the GPU), summarized by `scripts/summarize_benchmark.py` (`summary-n24.json`). Two repeats per condition.

FP16 evaluation, one prompt per call (the same evaluation as G3 to G5):

| condition | T of a generation, steady state (s) | 95 % interval | speed-up over B0 | candidates (wait) | update |
|---|---|---|---|---|---|
| B0, one process | 48.9 | 1.3 | 1.00 | 41.9 s | 7.7 s |
| B0x2 | 35.7 | 0.9 | 1.37 | 27.1 s | 8.0 s |
| B0x3 | 34.2 | 1.8 | 1.43 | 25.1 s | 8.1 s |

For comparison, G5 measured 221 s per generation for the same B0 (N = 24): **4.5 times faster with the thread pool alone, same bits** (every run, with one, two or three
processes, ended with the same rewards and the same weights hashes: `consistent` in the summary). A generation of B0 is 24 candidates of 1.7 s plus an update of 7.7 s.

FP32 forward pass, 16 prompts per call (`../2026-10-07-g6-local-scaling-fp32/`, the option of numerical contract section 15):

| condition | T steady (s) | 95 % interval | speed-up over B0 | candidates (wait) | update |
|---|---|---|---|---|---|
| B0 | 36.2 | 7.0 | 1.00 | 28.1 s | 8.0 s |
| B0x2 | 30.0 | 7.3 | 1.21 | 21.2 s | 8.0 s |
| B0x3 | 30.4 | 3.2 | 1.19 | 21.1 s | 7.9 s |

6 times faster than G5 for the same N, and about 1.35 times faster than the FP16 reference path of the same session. The intervals are wide (two runs, Student t); the gain of a second
process is real but smaller than for FP16, and a third process adds nothing: the CPU (28 threads shared by two or three noise pools and the coordinator's update) and the update (8 s
for 24 candidates, a quarter of a generation) are what is left.

Not measured: another N, the 1660S (see `../2026-10-07-g6-benchmark*/`), a longer rollout.
