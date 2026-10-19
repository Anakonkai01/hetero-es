# G7: restore trade-off, a longer workload, and a CUDA noise engine that is the same on two GPUs (07/10/2026)

Three questions, one folder. Everything was run by the AI on the two machines (RTX 5070 Ti, GTX 1660 SUPER; both torch 2.13.0+cu132); the owner has not
reviewed it. The tables are printed by `summarize.py` and `simulate_generation.py` from the JSON files here, not typed by hand.

## 1. A workload with a long rollout (`cot_workload.py`, `calibrate_workload.py`, `calibration-*.json`)

The workload of the contract answers in at most 16 tokens (0.16 s of rollout). Here the model reasons step by step (up to 256 new tokens);
the questions are generated from a seed, the answer is computed, the reward is the exact integer. Base model, FP32 forward pass, 32 questions, chunk 16:

| level | what | accuracy (both GPUs) | tokens | rollout 5070 Ti | rollout 1660S |
|---|---|---|---|---|---|
| 1 | two-digit `+ - *` | 0.562 | 3,392 | 3.5 s | 24.1 s |
| 2 | three operands | 0.969 | 3,631 | 3.8 s | 22.4 s |
| 3 | word problem (boxes of pens), **used below** | 0.281 | 7,054 | 4.4 s | 29.8 s |

The accuracy and the number of tokens are the same on the two GPUs (FP32 forward pass), for the three levels. Level 3 gives a signal (0.28, room to
learn) and a rollout 27 times longer than the 16-prompt workload. The rollout depends on the candidate (1.1 to 4.4 s on the 5070 Ti): a greedy reply
that does not stop before 256 tokens costs more, and a reply cut at 256 tokens has no answer.

## 2. Noise source and way back (`restore_tradeoff.py`, `tradeoff-*.json`)

24 candidates (seeds 0 to 23, sigma 1e-3), 32 questions of level 3, FP32 forward pass, chunk 16, CUDA-synchronised timings (median over candidates).
Four arms, a 2 x 2: the noise is made on the CPU (the contract engine) or on the GPU (`torch.Generator`, seed mixed with the tensor name, FP16 `add_`, as
es-at-scale and Agentic-ESOpt), and the model comes back by the verified snapshot restore or by arithmetic (`-sigma`, the noise generated again).

| | back by snapshot | back by arithmetic |
|---|---|---|
| **CPU noise** | A | B |
| **GPU noise** | D | C |

| GPU | arm | perturb s | rollout s | back s | candidate s | elements off after 24 candidates | relative L2 |
|---|---|---|---|---|---|---|---|
| 5070 Ti | A | 0.728 | 4.30 | 0.137 | 5.17 | 0 | 0 |
| 5070 Ti | B | 0.732 | 4.25 | 0.731 | 5.73 | 125,083,778 (25%) | 1.36e-04 |
| 5070 Ti | C | 0.009 | 3.80 | 0.009 | 3.82 | 125,080,011 | 1.36e-04 |
| 5070 Ti | D | 0.009 | 3.80 | 0.136 | 3.95 | 0 | 0 |
| 1660S | A | 3.583 | 28.85 | 0.490 | 32.99 | 0 | 0 |
| 1660S | B | 3.598 | 28.86 | 3.630 | 36.05 | 125,083,778 | 1.36e-04 |
| 1660S | C | 0.052 | 29.04 | 0.052 | 29.16 | 125,080,371 | 1.36e-04 |
| 1660S | D | 0.052 | 28.95 | 0.491 | 29.50 | 0 | 0 |

What it shows:
- The cost of a candidate outside the rollout is the noise (CPU 0.73 s, GPU 0.009 s on the 5070 Ti; 3.6 s and 0.05 s on the 1660S) plus the way back
  (snapshot 0.14 s and 0.49 s; arithmetic with CPU noise 0.73 s and 3.6 s because the noise is made again; arithmetic with GPU noise 0.009 s and 0.05 s).
  With this workload, A spends 17 percent of a candidate outside the rollout on the 5070 Ti and 12 percent on the 1660S; D spends 4 and 2 percent.
- The arithmetic way back is NOT exact: after one candidate 26 million of 494 million FP16 elements differ from the original, after 24 candidates 125 million
  (25 percent), largest difference 3.9e-3. The drift grows like the square root of the number of candidates (relative L2: 2.76e-05 after 1, 1.36e-04 after 24;
  an extrapolation of this fit, not measured, gives about 3.4e-03 after 15,000 candidates). B and C drift identically, so the drift is the rounding of the way back,
  not the noise.
- Its effect on the answers is small here: the reward of the unperturbed model after 24 candidates is unchanged (0.281) on the 5070 Ti in arms A, B, C, D (one answer
  changed in C) and on the 1660S in A, B, D; in arm C on the 1660S it is 0.344 (4 answers changed): that machine's GPU noise is another noise, see 3. Arms A and B use the same seeds and
  the same noise: 22 of 24 candidate rewards are equal, 4 of 768 per-question outcomes differ.
- **A and B give the same counts of differing elements on the two GPUs (125,083,778, to the unit): the canonical noise and the contract arithmetic are the same bits
  on both. C differs between the machines (125,080,011 and 125,080,371): the native GPU noise is not.**
- The snapshot (arms A and D) costs 0.92 GiB of host RAM on each machine; the arithmetic way back costs none.

## 3. Is the native GPU noise portable? (`rng_portability.py`, `rng-*.json`; `bench_calls.py`, `bench-*.json`)

`torch.randn` with the same seed on the two GPUs, SHA-256 of the bytes. Reading the PyTorch source (`calc_execution_policy`): blocks of 256 threads, grid =
min(ceil(numel / 256), SMs x (max threads per SM / 256)), thread t writes the elements t, t+T, t+2T, t+3T with T = grid x 256. While one call makes at most T
elements the mapping does not depend on the GPU; T is at most 107,520 on the 5070 Ti and **22,528 on the 1660S**.

| elements per call | 1,000 | 4,096 | 16,384 | **22,528** | 22,529 | 32,768 | 65,536 | 1M and up |
|---|---|---|---|---|---|---|---|---|
| same on the two GPUs? | yes | yes | yes | **yes** | **no** | no | no | no |

Calls of 8,192, 16,384 and 22,528 elements in a sequence on one generator also agree; 32,768 and 65,536 do not. So the native GPU noise is portable
exactly up to the smaller GPU's thread count, and the maths of curand (log, sin, cos) gives the same bits on sm_75 and sm_120 when the mapping is the same.
A first text of `rng_portability.py` put the limit at 90,112 (wrong: it used numel / 1024); the file says so.

## 4. The CUDA noise engine (`src/heteroes/noise/cuda_engine.py`, `src/heteroes/es/cuda_ops.py`; `cuda_engine_crossgpu.py`, `cudaengine-*.json`)

A tensor's noise is a sequence of calls of 22,528 elements on one generator (`normal_` on prebuilt views of one shared buffer; same bits as `randn`, checked
by hash in `bench_calls.py`), seed derived by SHA-256 from (engine version, schema hash, candidate seed, parameter index, call size), float32 cast to float16,
then the arithmetic of the contract. On the real model, **on both machines the hash of all the weights after a perturbation (seeds 0, 1, 2) and after an update
of 8 candidates, the restore, and the noise fingerprint are equal** (`cudaengine-5070ti.json`, `cudaengine-1660s.json`: 8 of 8 hashes and the fingerprint).

| operation (whole model) | CPU canonical 5070 Ti | CUDA 5070 Ti | CPU canonical 1660S | CUDA 1660S |
|---|---|---|---|---|
| perturbation | 0.73 s | 0.08 s | 3.67 s | 0.58 s |
| update of 8 candidates | 2.4 s (G6) | 0.64 s | | (4.5 s, the coordinator is on the 5070 Ti) |

Two lessons on the way: the first version (`randn(out=)` in calls of 8,192) was only 2.4 times faster than the CPU on the 5070 Ti and no faster on the 1660S: the cost
is the Python launch overhead of the calls (60,000 per perturbation), not the GPU. With calls of 22,528 elements and `normal_` on views the perturbation went from 0.29 s to 0.08 s
on the 5070 Ti, and the generation of the noise of the whole model (`bench_calls.py`) from 0.95 s (`randn(out=)`) to 0.43 s on the 1660S and from 0.10 s to 0.06 s on the 5070 Ti.
A mutation survived on purpose: asking `randn` for a full call into a shorter slice gives the right values but writes past the buffer (PyTorch resizes the view);
the code uses `min(...)` and no test can see the difference.

## 5. What this does to a generation (`simulate_generation.py`, `sim-A.txt`, `sim-D.txt`)

A trace-driven ESTIMATE, not a measurement of the runtime: it replays the measured duration of every candidate of arm A (CPU engine) or arm D (CUDA engine)
through a dispatch rule, with a synchronization of 10 s for the 1660S and an update of 0.3 s per candidate (CPU) or 0.08 s (CUDA).
Speed-up over the 5070 Ti alone (B0), greedy (B3) and tail-aware (B4):

| N | CPU engine B3 | CPU engine B4 | CUDA engine B3 | CUDA engine B4 | B0 CPU / CUDA (s) |
|---|---|---|---|---|---|
| 8 | 0.886 | 1.000 | 0.707 | 1.000 | 41.1 / 27.9 |
| 24 | 1.056 | 1.091 | 0.983 | 1.087 | 123.4 / 93.4 |
| 48 | 1.133 | 1.133 | 1.045 | 1.103 | 246.7 / 186.8 |
| 96 | 1.132 | 1.131 | 1.051 | 1.123 | 493.4 / 373.5 |
| 192 | 1.143 | 1.143 | 1.119 | 1.127 | 986.9 / 747.0 |

(`sim-A.txt` and `sim-D.txt`). Reading: the CUDA engine makes a generation about 24 percent shorter for the fast machine alone (123 s to 93 s at N = 24: the noise
and the update are gone). The 1660S needs 30 s for a candidate that the 5070 Ti does in 4 to 5 s (7.5 times), so it can only help when there are many candidates to share and its
10 s synchronization is spread over them: tail-aware dispatch (B4) gains 9 to 14 percent from N = 24 up and never loses to the 5070 Ti alone, while greedy (B3) loses at N = 8
and, with the CUDA engine, also at N = 24 (0.983). The gain of the 1660S does not grow with the CUDA engine (it shrinks a little, because the fast machine got faster).

## 6. What limits the rollout, and is a bigger chunk exact? (`rollout_scaling.py`, `rollout-scaling-*.json`; `chunk_probe_cot.py`, `compare_chunk_probe.py`, `chunkprobe-*.json`)

The same 64 questions answered with different numbers of prompts per `generate()` call (the chunk), FP32 forward pass, the unperturbed model. Seconds per question:

| chunk | 5070 Ti | 1660S |
|---|---|---|
| 16 | 0.142 | 0.929 |
| 32 | 0.087 (1.6 times faster) | 0.489 (1.9) |
| 64 | 0.067 (2.1) | 0.283 (3.3) |

The time per question is almost inversely proportional to the chunk: the decode loop is limited by the latency of each step (8.6 ms at chunk 16 on the 5070 Ti against about 2 ms for the memory traffic of the FP32 weights, an estimate; 56 ms per step on the 1660S, whose old CPU launches the kernels), not by the arithmetic.
The text of the answers is the same at every chunk and on both GPUs (one SHA-256, `b50c51ce...`). The check on perturbed candidates (`chunkprobe-*.json`: the parent and candidates 0 to 23 of the CUDA engine, 64 questions each):
chunks 32 and 64 against chunk 16 on the 5070 Ti, 0 of 1,600 answers differ; chunk 64 against chunk 32 on the 1660S, 0 of 1,600; the two GPUs against each other at chunk 32 and chunk 64, 0 of 1,600 each; the 1660S at chunks 32 and 64 against the 5070 Ti at chunk 16, 0 of 1,600 each.
The benchmark that uses it is in `../2026-10-07-g7-bigchunk/`.

## What this does NOT show

- One workload, one model (Qwen2.5-0.5B), one pair of GPUs, 24 candidates per arm, one run per arm; no confidence intervals.
- The CUDA engine is NOT yet in the runtime: the recipe, the executor, the coordinator and the admission still use the CPU engine. The cross-GPU evidence is for
  these two GPUs and these software versions (torch 2.13.0+cu132); it has to be repeated when either changes (the fingerprint is the check).
- The simulation is an estimate with assumed synchronization and update costs, an optimistic tail rule (true durations as the estimate) and a trace repeated for N above 24.
- No learning experiment: the effect of the drift of the arithmetic way back on learning over thousands of candidates is not measured (only extrapolated).
- The time of the rollout depends on the candidate, so the totals of two arms with different noise are not directly comparable; the phases outside the rollout are.
