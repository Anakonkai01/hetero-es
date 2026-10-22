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

Candidate15 (packaging commit `004da17`; runtime `3fd3f301ef0a`, Windows Desktop runtime `0ce7d7013c33`)
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

## 4. Fault injection run (candidate15, GPU noise) — `fault/`

Declared in `fault/plan.md` before submission. Run `d1f6ad7bfdb34b47bf6a987a615949f2`: 24 candidates × 80 generations
on nhan, nhut and native Windows. Faults (`fault/fault-log.jsonl`, coordinator lifecycle in `fault/lifecycle.jsonl`):

| generation | fault | what the system did |
| --- | --- | --- |
| 6 | SIGKILL nhut's worker | **not injected**: the script looked one directory too high for `process.json` (fixed for the soak) |
| 14 | nhut: new outbound TCP rejected for 180 s, then the exact rule removed | the worker gave up, the coordinator started launch 1 when nhut answered again |
| 25 | `systemctl reboot` of nhut | 409 (device not ON yet) recorded as deferred, then launch 2 ~1.5 min after the reboot (lingering service, keep ON) |
| 34 | `taskkill /F /T` of the Windows app, normal relaunch, switch ON by UI Automation | deferred (409) until ON, then launch 1 |

Result: **COMPLETED 80/80 generations, 99/99 selected audits matched, no quarantine**. Independent ledger replay:
nhan with GPU noise and nhut with `HETEROES_NOISE_DEVICE=cpu` both **ALL EQUAL (80 generations)** with the same receipt
hash `708c0e01…` (`fault/replay-*`); no candidate text regeneration is claimed. 79 distinct parent hashes over 80 generations (78 of 79 transitions changed weights).

## 5. Soak

**Attempt 1 failed at generation 60: nhan's root disk was full** (`soak/attempt1-enospc/`, run
`f10720536eba436ba026d650edbb6f16`, `failureReason: OSError: [Errno 28] No space left on device`). The run ended
cleanly as FAILED with its final weights hash and a final recovery point; 69/69 audits had matched, the declared SIGKILL
of nhut's worker at generation 20 was restarted in 14 s. Cause: every finished run leaves ~5.6 GB of coordinator data
(recovery points, export, weights) under `~/.local/share/heteroes-worker/artifacts/coordinators/` and nothing removes it;
tonight's runs had added ~67 GB to a disk that was already ~85 % full, and the soak itself held 11 recovery points
(~1 GB each, hard-linked weights) while their upload to the lab lagged. Nothing checked free space.
Recovery: own packaged-check fixtures deleted (9.8 GB); the coordinator data of tonight's eight finished runs was copied
to the Archive disk (UUID verified), compared by size/path listing, and replaced by symlinks so the lab's result pages
still resolve (`soak/disk-move.log`); 62 GB free. Product fix (not deployed during the soak): `pause_check` in
`product/runner.py` pauses at the generation boundary when free space under the run's data directory is below
3 × model size + 1 GiB, with a `paused_low_disk` event; the pause keeps a verified checkpoint so the run can resume once
space is freed. Tests first, 4/4 mutants killed (`checks/low-disk-*`). Not exercised on a real full disk.
Open product question for the owner: a retention rule for finished runs' local coordinator data.
