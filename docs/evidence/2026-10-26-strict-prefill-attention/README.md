# Strict prefill query/head tiles — 2026-10-26

Runtime `2eb4da0d`, test-route fix `6cc69d26`, base `48547ba3`. Branch
`work/codex-frozen-perf-2026-10-25`. The owner requested session closure and handoff to Claude while the
native Windows check was running. **Native acceptance is pending in this sealed checkpoint.**

The new kernel stages K/V once across adjacent queries and query heads. Each warp owns one query/head slot.
The planner bounds the launch to 512 threads, 48 KiB shared memory and at most 256 keys. Aligned, pruned
denominator/value subtrees preserve every rounded operation, signed-zero flush and failure check, including
masked K/V loads. Other shapes and device-built decode layouts retain the existing GQA/split kernels.
Tile descriptors are call-local and reused across layers; they retain no weights or candidate/KV content.
The source fingerprint includes the new planner/CUDA module. Historical noise/update/replay arithmetic is unchanged.

## Whole-generation measurements

ABAB separate processes, two processes per version and five warm samples per process; the table uses the median
of their process medians. All token hashes agree. These final 5070 Ti runs were made after the CPU/packaging jobs
finished. Compare these paired baselines, rather than interpreting the previous CPU-contended 8580 as the baseline.

| Host | Model/case | Base | Query tiles | Gain |
| --- | --- | ---: | ---: | ---: |
| 5070 Ti Linux | Qwen short32 | 8746.3 | 8922.1 | +2.01% |
| 5070 Ti Linux | Qwen chat128 | 8865.7 | 9108.7 | +2.74% |
| 5070 Ti Linux | Smol short32 | 8372.1 | 8526.7 | +1.85% |
| 5070 Ti Linux | Tiny short32 | 4534.6 | 4644.3 | +2.42% |
| 3060 WSL2 | Qwen short32 | 2693.2 | 2747.2 | +2.01% |
| 3060 WSL2 | Qwen chat128 | 2638.3 | 2693.0 | +2.07% |
| 3060 WSL2 | Smol short32 | 2666.5 | 2786.5 | +4.50% |
| 3060 WSL2 | Tiny short32 | 1380.6 | 1404.8 | +1.76% |

Qwen short32 is about **64.5%** of the historical vLLM control, 13835 token/s. The performance objective remains open.
`summary-5070-wsl2.json` is explicitly partial. Recompute into a fresh path with:

```bash
python3 docs/evidence/2026-10-26-strict-prefill-attention/summarize.py \
  --without-native --out .scratch/fresh-prefill-summary.json
```

CUPTI, Qwen chat prefill: attention **25.29 → 12.26 ms**, whole prefill about **118.7 → 106.8 ms**;
projections remain **71 ms**. Operator pilot **1035 → 504 µs**. Raw baseline/selected profiles and pilot receipts
are in `raw/`. Pilots are not separate whole-model acceptance claims.

## Correctness and packaging

- 5070 Ti: **458 GPU tests passed**, including attention, packed/graph/integer decoders and fused finishes.
  New kernel PTX/SASS audits passed for SM75/80/86/89/90/120 and four dimension/tile configurations.
- 3060 WSL2: **1002 passed in 865.71 s**, exit 0, `raw/3060-wsl2-01/tests-3060-repaired-02.log`.
  The first import failure was a missing isolated `py.py` pytest shim, not a numerical failure; that log is retained.
- Trained Qwen/Smol/Tiny parent, canonical seed 7001 ±sigma and restored parent match in weights, prefill logits,
  tokens and rewards across both GPUs, and match the sealed fused-finish receipts. Qwen EOS captured = uncaptured,
  27/32 rows ending early, and identical to the sealed receipts. This was an actual full uncaptured run on both
  Linux/WSL2 hosts. Qwen WSL2 took 1029 s, consistent with the previous 1013 s receipt.
- Mutation: **10/11** initially; the surviving mutation disabled the default route while a fixture explicitly
  enabled it. `6cc69d26` removes that override; control passes and the mutation is killed **1/1**. The ten original
  arithmetic/layout mutations were all killed, including missing query/K/V flushes and incorrect masks/tree roots.
- `scripts/check-all.sh`: **ALL PASS**. Runtime CPU **3237 passed / 884 skipped**; backend **452 passed**;
  frontend/desktop units, lint/format/types/i18n, browser and Electron fixture checks passed.
- `build-apps --check`: passed. The Worker archive matches **all 142 runtime Python files byte for byte**, including
  `strict_prefill_cuda.py`. Receipts/archive hashes were retained and the 910 MiB scratch packaging tree removed.

The full uncaptured Qwen EOS probe on the 5070 Ti logged an allocator retry under VRAM pressure but completed
with status `ok` and exact results. These finite probes do not establish a managed VRAM admission bound.

## Native Windows is still running

See [the handoff](../../handoff-claude-after-codex-prefill-2026-10-26.md). The native source archive/manifest is already
verified and its SHA256 is recorded under `raw/3060-native-01/`. The console snapshot is partial; the live console is
outside this sealed evidence folder at `.scratch/codex-prefill-20261026/native-live-console-01.log`.

Native runs the current GPU suites, all four Qwen states and a fresh captured 32-row real-EOS generation. It compares
that EOS generation with the **sealed uncaptured oracle**, after verifying model files/schema/weights, workload,
canonical states and EOS options. It does **not** relabel that old uncaptured run as a newly executed native run.
This avoids repeating the expensive uncaptured control while retaining an exact token comparison.
The binding helper has **15 CPU tests**, **7/7 mutations**, and a successful full local integration replay
(`frozen-eos-integration-5070ti-01.json`, 32 s). The native receipt records `uncapturedEosControl.measuredInThisRun=false`.

Do not append native results here after sealing. Collect them into a fresh follow-up folder, then use
`summarize.py --native-dir <fresh native receipts> --out <fresh summary>` without `--without-native`.

## Unselected experiments

Replayable scratch copies are under `harness/experiments/`; they are not selected runtime changes.

- Projection tile **64 rows × 32 columns**: eight local bit/oracle tests passed, but five operator shapes ranged
  from unchanged to about **5% slower**. More activation/shared loads offset amortized weight conversion.
  `projection_rows32.py` is this version; the bench's import must select that version when replaying run 01.
- Projection tile **64 × 64**, dynamic 60 KiB shared memory: eight local tests passed, but operators were about
  **18–42% slower**. `projection_rows.py` is an operator-only prototype; its dynamic-buffer interception must not
  be installed into a whole decoder (other stream launches do not supply its dynamic shared-memory argument).
- GQA denominator warp trees and eight-slot value counters: **53 local bit/flag/oracle tests passed**, but gains
  were only **0.6–2.7% per operator**, with unchanged 82 registers/thread. No whole-model gain, mutation,
  cross-architecture, cross-GPU or native acceptance was established. Not selected.
- The early prefill pilots must be replayed against the archived `48547ba3` source: their baseline selector
  assumed the old default GQA path. The integrated runtime and final ABAB receipts are authoritative.

## What this does NOT show

Completed native Windows acceptance for this checkpoint, near-vLLM performance, learning/quality effects, broad
hardware/model qualification, managed ownership/activation or completion of M0–M6. No push, merge, deployment,
device-state change, learning run or modification of the `ai` environment was made. The initial remote job was
interrupted by a machine reboot; no completed test result was claimed from that lost stage.
