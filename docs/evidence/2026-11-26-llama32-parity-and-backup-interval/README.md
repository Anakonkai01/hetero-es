# 2026-11-26: Llama-3.2-1B strict parity golden (RTX 5070 Ti) and the recovery-point interval on one GPU

Recorded overnight on 26/11 on the project workstation (RTX 5070 Ti, SM120, driver 595.91, torch 2.13.0+cu132). The
borrowed RTX 3060 machines were off, so everything here comes from ONE GPU.

## 1. Llama-3.2-1B-Instruct with the strict decoder (llama3 RoPE)

Model `unsloth/Llama-3.2-1B-Instruct` revision `5a8abab4a5d6f164389b1079fb721cfab8d7126c` (GQA 32/8 heads, RoPE
`llama3`, vocabulary 128,256). Probe `acceptance/probes/strict_parity.py` (working branch commit 44024005 plus the
workload fix that follows it), chat workload `acceptance/golden/workload-chat-llama32.json` (the 64 GSM8K questions of
`workload-chat-01.json` in Llama 3.2's chat template, date pinned).

| File | What it is |
| --- | --- |
| `record-5070ti-01.json` | `--record` run: parent, +σ and −σ candidates (seed 7001, σ = 1e-3, noise v2) and exact restore; tile and stream projection schedules; short8 and chat32×128 workloads; real-EOS decode of 32 chat rows, 351 new tokens (31 rows end early). Status `recorded`, tile = stream in every state, restore exact. |
| `compare-5070ti-01.json` | The ordinary comparison run against `acceptance/golden/strict-b22-llama32.json` (built from the record by `make_llama_golden.py`), same GPU, new process: `PARITY OK`. |

Also on 26/11 (not a receipt here): 32 GSM8K validation rows at 512 tokens through `runner.score_model`, twice: 9/32
correct, no row cut at 512 tokens, the same SHA-256 of all outputs both times.

**What this does NOT show:** that another GPU type gives the same tokens. The golden comes from one SM120 card; the
cross-GPU claim for Llama needs the same comparison run to pass on the RTX 3060 (SM86). Nothing about answer quality or
learning; no lab qualification or lab run with Llama yet (E2 waits for the borrowed GPUs). Llama is not part of the
registered 37-pair acceptance matrix.

## 2. Recovery point every 10 generations instead of every generation (one RTX 5070 Ti)

Two lab runs of the E4 configuration (Countdown, Qwen2.5-1.5B-Instruct continued from E4's verified generation-110
point, parent weights `2d3ede91…`, 32 candidates × 32 rows, 384 tokens, α = 5e-4, σ = 1e-3, coordinator and worker on
the same 5070 Ti):

- `5f0c79f0…` (25/11): recovery point every generation, 6 generations (E4's 1-GPU reference);
- `6131a0ad…` (26/11): every 10 generations (new default), 16 generations; recovery points at generations 9 and 15.

`speed_backup10.py` reads the coordinator's `events.jsonl` (validation generations left out) and wrote
`speed-backup10.json`:

| Seconds per generation | every generation (5 gens) median / mean | every 10 (15 gens) median / mean |
| --- | --- | --- |
| scoring the candidates | 84.8 / 86.1 | 83.5 / 88.8 |
| ES update | 11.5 / 10.5 | 8.7 / 10.2 |
| publish weights | 1.1 / 1.2 | 1.5 / 2.0 |
| recovery point + opening the next generation | 7.8 / 8.9 | 3.2 / 5.0 (34.4 at the generation that writes a point) |
| whole generation | 112.0 / 106.8 | 102.5 / 106.1 |

The step the change targets shrinks as expected (median 7.8 → 3.2 s). The whole generation is dominated by scoring,
which varies by tens of seconds between generations (77–117 s; each generation scores different train rows and the two
runs use different noise seeds, so their answers differ), so with 5 and 15 generations the total is not measurably
different (median −9.5 s, mean −0.7 s).

**What this does NOT show:** a multi-GPU measurement (the 2- and 4-GPU effect is an estimate); a controlled benchmark
(5 vs 15 generations; generations 3–7 of the new run overlapped a screen recording and video encoding on the same
machine); identical weight chains (noise seeds are per run, by design).
