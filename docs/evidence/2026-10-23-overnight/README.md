# Overnight 22→23 Oct 2026: speed, faults, soak and engine v2 on the GPU

Owner went to sleep at ~00:05 and authorized an autonomous night (Claude): close candidate14, then measure speed with
1→2→3 machines, inject faults, run a long soak, and make engine v2 on the GPU with bit parity on three machines.
Machines: 5070ti-nhan (coordinator + worker), 5070ti-nhut, native Windows 3060-thao. Quang and the 1660S are offline
(the owner dropped the 1660S). Model: Qwen2.5-0.5B-Instruct, FP32 evaluation, twenty multiplication rows, last-integer.
These are system runs, not learning experiments.

(Sections are filled in as the night goes; see the bottom for what this does NOT show.)

## 1. Speed 1→2→3 machines, CPU engine v2 (candidate14e agents)

Same declared run each time (`speed/*/declared.json`): 48 antithetic candidates, 4 generations, batch 8, 32 new
tokens, coordinator nhan. Records: `speed/m*/{submission,final,timeline,results}.json`, `summary-cpu-v2.json`.

| machines | wall (s) | per generation: wait for candidates / coordinator update (s) | audits |
| --- | --- | --- | --- |
| 1 (nhan) | 375.9 | ~57 / ~11 | 12 selected, none possible with one worker |
| 2 (nhan, nhut) | 249.4 | ~36 / ~12 | 8/8 matched |
| 3 (+ Windows 3060) | 315.2 | ~37 / ~12 | 8/8 matched |

The third machine did not help: every generation carries ~11 s of coordinator update (engine v2 noise of 48 candidates
made on the CPU) and every worker replays that update before it evaluates, so a slower machine adds waiting, and its
start-up is longer. One sample per cell; the 3-machine wall also contains a longer start.

The first 3-machine attempt (`speed/m3-stuck-start*`, `finding-stuck-start/`) stayed STARTING: the lab edge had timed
out around 00:00-00:07 and two START requests from the coordinator never reached the lab; polls then answered
"waiting for worker acknowledgement" forever. It was cancelled. Fix `b66496e` (tests first, 5/5 mutants killed,
`checks/supervisor-*`): a start whose outcome is unknown is sent again with the same launch number (the lab keeps one
start per assignment, device, recovery and launch).

## 2. Engine v2 on the GPU (same bits, numerical contract 18.1)

`gpu-v2/`: prototype (`proto_pcg.py`), probes and timings. Chunks made on the GPU equal the CPU engine bit for bit on
nhan (5070 Ti, glibc 2.43), nhut (5070 Ti, glibc 2.39) and native Windows (3060): 64 chunks with a tail give the same
SHA-256 `286343dd…` everywhere (`probe-*-source*.json`). Perturb + update of a toy model with integer weights give the
same hash `b2afd6a7…` on all three machines, GPU path = CPU path on each (`probe-*-fixed.json`; with torch's random
initialisation the Windows base weights differ from Linux, which is torch's CPU RNG, not ES arithmetic).
Real Qwen 0.5B on nhan (`real-model-nhan-batched.json`): equal perturbed and updated hashes for both paths, perturb
0.68 s → 0.09-0.14 s, update of 48 candidates 20.4 s → 3.2 s (two samples each). GPU tests and 10/10 mutants:
`checks/gpu-v2-mutation.log`.

## 3. Speed again with candidate15 (engine v2 made on the GPU by default)

Candidate15 (`f…` packaging commit after `d1912f3`; runtime `3fd3f301ef0a`, Windows Desktop runtime `0ce7d7013c33`)
was published and installed: nhan by the public `install-worker.sh`, nhut by `heteroes-worker update`, native Windows
by Quit safely → silent install of the prepared hash → app RPC install + GPU self-test → normal relaunch without debug
ports → switch ON by UI Automation (`upgrade-*-c15*.log`, `install-c15.ps1`). Same declared runs, same candidate seed
namespace (`speed-gpu/`, `speed-gpu/summary-cpu-vs-gpu.json`):

| machines | CPU v2: sum of generations / wall (s) | GPU v2: sum of generations / wall (s) | update per generation (s) |
| --- | --- | --- | --- |
| 1 | 302.0 / 375.9 | 110.0 / 186.6 | ~11 → 2.3 |
| 2 | 192.1 / 249.4 | 75.7 / 153.2 | ~12 → 2.3 (one 14.4 outlier) |
| 3 | 199.7 / 315.2 | 68.7 / 149.4 | ~12 → 2.3-3.4 |

All six runs have **the same parent-weights hash at every generation** (`c9118c8a…`, `e3923dc8…`, `65371460…`,
`db9e4737…`): 1, 2 or 3 machines, CPU or GPU noise, Linux or Windows workers. All audits matched. Start-up (~75 s) now
dominates such short runs. One sample per cell; not a benchmark of the model or of ES.
