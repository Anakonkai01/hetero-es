# Handoff to Codex: strict B22 decode after Claude's 2026-10-26 evening session

Branch `work/codex-frozen-perf-2026-10-25`, worktree `/home/pc5070ti/projects/heteroes-codex-frozen-perf`. Nothing
pushed, merged or deployed; lab and devices untouched. Read `docs/HANDOFF.md` first, then this page.

## State

Owner goal (unchanged): own strict kernels near the vLLM control (Qwen batch 32 short32 **13835** token/s on the
5070 Ti), then M0–M6. Every change below keeps B22 arithmetic bit for bit (same tokens, logits and flags).

| Commit | Change | Evidence |
| --- | --- | --- |
| `878018e3` `22511cdf` `96bec7d1` `d4030b52` | streamed projections, queued decode step, grouped QKV / gate+up, fused RMSNorm/SiLU quantization, tests closing mutation gaps | `evidence/2026-10-26-strict-projection-shapes/` (sealed) |
| `5cc72926` | fused finishes: Q/K/V + RoPE + cache store, gate/up + SiLU + row max + packing, residual add; shuffle-tree RMS quantization | `evidence/2026-10-26-strict-fused-finish/` |
| `96e2a0db` | split-K tests independent of GPU size (the 3060 plans differ) | same |
| `fd7418a2` | greedy selection split over 8192-column chunks (69 → 21 µs/step) | same |
| `ac3c6f4c` `e3293fb1` | fewer host stalls around prefill, prefill RMSNorm fused with quantization, parallel prefix cache copy | same |
| `1c9a54b9` | decode projections through 32-column CTAs (8 columns per warp); prefill keeps 64 | same |

Qwen batch 32, 5070 Ti: `75f92c30` 4761 → `d4030b52` 7589 → `1c9a54b9` **8580** short32 (**8722** chat128; paired ABAB, measured while a CPU-heavy packaging check ran).
See the evidence README for every host and model.

## Where the time goes now (5070 Ti, Qwen B32, CUPTI)

- Decode step about 2.44 ms at short context (324 kernels): projections ~1.6 ms, attention 0.31 ms
  (13 µs/layer; 32 µs/layer at 270 keys), RMS/finish/pack/input/greedy ~0.45 ms.
- Measured int8 `mma.sync m16n8k32` peak 410 TOPS; plain DRAM read 845 GB/s; L2 48 MB. B22 decode needs
  ~285 GOP per step: the GEMM is close to balanced between MMA and DRAM. Large shapes already reach ~85–90% of the
  kernel's own memory-only rate; the loss is per launch (ramp, wave quantization: gate/up has 304 CTAs for 140
  resident slots, two CTAs per SM limited by registers and shared memory).
- Prefill: ~42 ms of a short32 generation (888 tokens), ~121 ms of chat128 (2879 tokens). Projections run at
  ~260 TOPS (63% of peak); attention prefill ~25 ms for chat (one block per query, latency-bound).
- Scripts (scratch, not evidence): `.scratch/claude-opt-20261026/step_trace.py` (one captured decode step, kernel by
  kernel), `prefill_trace.py` (prefill kernels, idle gaps, host profile), `gemm_rate.py`, `peak2.py`.

## Tried and rejected (measured this session)

- Programmatic dependent launch for every kernel, with or without an L2 prefetch before the wait: step 2672 → 2766 µs.
- L2 prefetch of the next weights from a parallel graph branch or inline: GEMMs faster, step slower (2655 → 2810).
- Cluster/DSMEM attention (aligned key chunks per CTA): 13.6 → 112 µs/layer, because the graph sizes clusters for
  512 keys and idle CTAs still wait at every cluster barrier.
- Fused SiLU quantization in prefill (one CTA per row for 888–2879 rows): slower than silu_mul + quantize.
- Different split-K choices: QKV/o split 7 no change; gate/up split 3–4 about −1.3% (not adopted: the plan, the
  workspace bound and identity would need stream-specific geometry).

## Next work, in order of measured opportunity

1. Prefill attention: a query-tile kernel (K/V staged once for 8–16 queries × 7 heads; scores kept in shared memory
   because prefill spans are ≤ max_keys) with the same aligned trees as `strict_attention_gqa`. ~20 ms of chat128.
2. Prefill projections with larger row tiles or digits converted once into shared memory and shared by row warps
   (now ~63% of MMA peak, weight conversion repeated for every 32-row tile).
3. Decode attention at long context (32 µs/layer at 270 keys). Clusters failed; consider a dynamic aligned chunk
   per CTA within one CTA's keys or fewer barriers (warp-shuffle trees as in the new RMS quantization).
4. Decode projection waves (persistent/balanced split with variable segments into the existing finishes).
5. After the performance goal: M0–M6 per `docs/HANDOFF.md`.

## Gates used (repeat for every change)

Tests first and bit/flag comparisons against the unfused or original kernel and the CPU oracle; multi-architecture
PTX/SASS audit (`test_*_source_passes_*_audit_on_other_architectures`); `scripts/mutation-check.py` from a frozen
`git archive` copy (`--repo <copy>/runtime`), so the working tree can change while it runs; trained parity
(`evidence/2026-10-26-strict-fused-finish/harness/`: `stage.sh <out> <base>`, `local_5070ti.sh`, `remote_3060.sh`
with `RUN=NN`); 3060 WSL2 via `thao_nguyen@100.92.20.58` (commands in the earlier Codex handoff); native Windows via
`evidence/2026-10-26-strict-projection-shapes/harness/run_native_01.py` (fresh file names on the Windows cache).
Timing needs an idle GPU: a mutation run on the same GPU distorts wall-clock throughput (CUPTI kernel times are
mostly stable). `pgrep -f`/`pkill -f` can match your own shell; kill by PID.

## Open items from this session

- Native Windows run of `5cc72926..1c9a54b9` (the base `d4030b52` passed natively; see the sealed folder).
- gate/up split 3–4 (−1.3%) needs stream-specific plan geometry in `integer_plan` and the workspace bound.
- `scripts/check-all.sh` was last run at `96bec7d1`; the targeted GPU and CPU suites above ran on the final source.
- 3060 gains are small for Qwen (+3–4%): its decode is bound by 360 GB/s weight reads, not by the fused glue.
