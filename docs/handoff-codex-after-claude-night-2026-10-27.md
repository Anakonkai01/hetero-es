# Handoff to Codex after Claude's night session — 2026-10-27

The owner closed the Claude session at about 00:05 +07 to save usage. Worktree
`/home/pc5070ti/projects/heteroes-codex-frozen-perf`, branch `work/codex-frozen-perf-2026-10-25`, HEAD after this
page's commit. Nothing pushed, merged or deployed; lab/devices untouched; no learning run; `ai` env unchanged.
Read `AGENTS.md`, `docs/HANDOFF.md`, `runtime/docs/numerical-contract.md`, then this page.

## State in one paragraph

Native Windows acceptance of Codex's prefill tiles finished OK and is sealed (`a7884392`,
`evidence/2026-10-26-strict-prefill-native-finish/`). Claude then committed `7ca91112`: prefill 64-column GEMM
with two stages at three CTAs/SM, and the request weight-exponent refresh as one batched launch. Qwen B32 on the
5070 Ti: short32 **8913 -> 9155 (+2.7%)**, chat128 **9107 -> 9240 (+1.5%)**, identical token hashes
(`evidence/2026-10-27-strict-prefill-gemm-weights/`). That folder is a partial checkpoint (gates below are open).
Qwen short32 is ~66% of vLLM 13835. The goal is still open; M0–M6 remains after performance work.

## Open gates for `7ca91112` (do these first, they are cheap relative to new work)

1. 3060 WSL2 full runtime GPU suite and timing (the SM86 occupancy of the new prefill setting is unmeasured; if it
   is slower there, make `PREFILL_STAGES/PREFILL_MIN_BLOCKS` arch-dependent, e.g. only `sm_120`).
2. Native Windows run (fresh `-02` names on the Windows cache; see the prefill-native-finish README for the
   receipt checks and `evidence/2026-10-26-strict-prefill-attention/harness/run_native.py`).
3. Trained parent/±/restore + EOS parity on both GPUs with `evidence/2026-10-26-strict-fused-finish/harness/`
   (`stage.sh`, `local_5070ti.sh`, `remote_3060.sh`) against the sealed receipts.
4. Mutation from a frozen `git archive` copy (`scripts/mutation-check.py --repo <copy>/runtime`) on
   `integer_weights_batched` (max update, exponent formula, flag, row index, routing condition) and on the
   prefill defines (none should change bits; a stage-count mutant is an equivalent mutant — say so).
5. `scripts/check-all.sh docs/evidence/<new>/checks` and the Linux packaging check, then seal a fresh folder.

## Why the remaining gap is hard (measured, see the evidence README)

- B22 needs 9 int8 IMMAs per multiply-accumulate. At B32 decode the GEMMs are MMA-bound (~80% of peak inside the
  K loop) at about the DRAM time: gate/up takes 24.6 us even with weights warm in L2. Persistence, stage counts,
  warps/CTA and L2 prefetch did not help (table of rejected pilots in the evidence README; diffs in `rejected/`).
- Attention and glue are latency chains of strict FP32 ops (~0.85 ms/step). Key-split attention was bit-exact
  but only +0.3–0.6% end to end; residual+RMS fusion was slower. Do not repeat these without new evidence.
- Speculative/population proposals were already measured by Codex (evidence `2026-10-26-strict-speculative`) and
  lose at batch 32. Karatsuba/digit tricks change B22 arithmetic or do not fit int8.
- Claude's estimate (inference, not measurement): with all remaining ideas ~75–80% of vLLM at B32 short32.
  Tell the owner plainly if the target needs a decision (e.g. accept a ceiling, or measure at the ES batch size).

## Next work, in order: exact bounded lm_head argmax (approved by the owner: "oke làm luôn")

lm_head is ~355 us of the ~2.47 ms decode step (272 MB FP16 read for one greedy token per row) plus ~16 us of
greedy. Feasibility (`evidence/2026-10-27-strict-prefill-gemm-weights/lmhead-feasibility/output.txt`): with
weights truncated to 7 signed bits, a rigorous integer bound leaves median 1, mean 1.94, max 13 of 4748 tiles
(32 tokens) per row; the true argmax always survives. Expected: lm_head+greedy ~370 -> ~185 us/step,
about +4.5–5% whole generation for short32 and chat128 (estimate from operator numbers, not yet measured).

### Arithmetic and proof obligations

Notation per decode row r and vocab row v: `qa` (B22 activation, 22-bit, from the packed planes of
`rms_norm_quantized(final norm)`), `qw = quant_half(w, ew[v])` with `|qw| < 2^22`, exact `S = sum_k qa*qw`
(what the GEMM computes), score `fl(v) = encode(S, ex[r]+ew[v]-42)` then strict `load` (flush+note) in greedy.

- Request begin: `t[v][k] = floor(qw / 2^15)` stored as int8 (always in [-128, 127]); `0 <= qw - 2^15 t < 2^15`.
- Per row (small pre-kernel from the planes): `Q1 = sum qa`, `L1 = sum |qa|` as int64.
- Bound GEMM: `P = sum qa*t` exactly (activation 3 digits x t: **3 IMMAs per k32 instead of 9, 1 byte per weight**),
  `S' = 2^15 P + 2^14 Q1`, `b = 2^14 L1`, so `|S - S'| <= b` exactly (integers, no rounding).
- `hi = bound_encode(S'+b)`, `lo = bound_encode(S'-b)`: same RNE mapping as `encode` but **without** touching the
  error flag (return +/-inf on overflow). RNE is monotone, so `lo <= fl(v) <= hi` in float order (-0 == +0).
- Survivors: tile T survives if `max_{v in T} hi >= max_{all u} lo` (ties included) **or** any element of T has a
  nonfinite `hi` or `lo`. The true winner (largest score, smallest index on ties, as `decode_greedy`) and every
  tie partner survive: `hi(v*) >= fl(v*) >= fl(u) >= lo(u)` for all u.
- Flags: in every non-surviving tile all bounds are finite, so every exact logit there is finite and the full
  path would raise nothing there. Surviving tiles are computed exactly with the real `encode` (overflow flag),
  the GEMM epilogue's nonfinite check and greedy's `load` -> identical flags and tokens.

### Kernels (put them in `integer_cuda.py` or a new module included in the source identity)

1. `bound_weights` (request begin, after exponents): FP16 lm_head -> int8 `t` (136 MB for Qwen). Retained buffer
   (the decode graph captures its pointer): zero it in `_end_request` like the exponents, and add `V*K` bytes to
   `IntegerDecoderGraph._request_workspace_bytes`. Cost ~0.5 ms/request (read 272 MB, write 136 MB).
2. `bound_rows`: `Q1`, `L1` per decode row from the planes (`qa = d0 + 256 d1 + 65536 d2`, signed digits).
3. `bound_scores`: copy of the 32-column decode stream kernel with an int8 weight stage (32 rows x 64 bytes per
   stage) and **no conversion**: keep the existing K permutation — for k32 step s, thread `thread` takes the
   8 contiguous bytes `t[v][32s + 8*thread .. +7]` as `b[0]=.x` (K 8t..8t+3) and `b[1]=.y` (8t+4..8t+7), the
   same physical K the FP16 path packs into `lo/hi`; A fragments exactly as now. Accumulate one int32 per
   activation digit (3 MMAs per m-group), combine `P = sum_d 2^(8d) acc_d` in int64 in the epilogue, compute
   `hi/lo` per element and reduce per (row, CTA tile): `tile_hi[r][T]`, `tile_lo[r][T]` (float, ~1.2 MB total for
   B32). Columns past V are excluded; a nonfinite element bound sets `tile_hi = +inf`.
4. `bound_select`: grid (rows, Z) with Z ~ 8; each CTA computes `global_lo = max_T tile_lo[r][T]` (4748 floats),
   then walks tiles `T = z, z+Z, ...` (keep runtime-stride loops rolled — `#pragma unroll 1`, no precomputed trip
   count; an unrolled count lowers to MUFU.RCP which the audit rejects, seen tonight) and, for surviving tiles,
   computes the 32 exact logits (int64 dot of `qa` and `quant_half(w)`, `encode`, bias if any, nonfinite flag,
   then `flush`/`note` as `load`), keeping (best score, smallest index). Write per (r, z) best to buffers and
   reuse `decode_greedy_select` (chunks = Z) for tokens/seen/result/flag. Worst case (all tiles survive) is slow
   but still exact — no host fallback is needed.
5. Integration: add a hook in `StrictDecoderGraph._decode_core` (base) for "final norm + lm_head + greedy";
   `IntegerDecoderGraph` uses the bounded path only when rows > 1, `state.penalty == 1.0` (the bound is not
   penalty-aware; keep the existing path otherwise — the capture key already includes the penalty), lm_head has
   no bias (or add the bias exactly in step 4 and widen the bound by nothing: bias is added after encode, so
   apply it to both hi and lo with `add_rn`, which is monotone), the stream path is eligible and widths fit.
   Prefill's first token keeps the existing exact lm_head (once per request).

### Tests to write first

- Bounded selection equals the full `linear_decode` + `greedy` on random and trained-Qwen rows: tokens, `seen`,
  `result`, flags; ties (duplicate vocab rows with equal and with smaller indices), all-equal rows, -0/+0,
  subnormal-flush cases, a vocab not a multiple of 32, rows <= 16 and 17..32.
- Adversarial bounds: construct weights/activations so that many tiles survive (all tiles) and so that one
  non-winning tile overflows (`encode` overflow) -> same error flag as the full path.
- Premise checks: the bound really contains `S` for random data (assert `lo <= fl <= hi` elementwise).
- Request lifecycle: `t` rebuilt after in-place weight change and restore, cleared after the request, buffer
  pointer stable across requests; penalty != 1 uses the old path; graph capture count unchanged.
- PTX/SASS audit of the new kernels on sm_75/80/86/89/90/120 (pattern:
  `test_ops_source_passes_the_instruction_audit_on_other_architectures`).
- Mutants to kill: drop `+b`/`-b`, use `>` instead of `>=` for survival, drop the nonfinite-survival rule, off-by-one
  tile index, wrong digit weight in `P`, tie rule.

Then measure ABAB with `evidence/2026-10-27-strict-prefill-gemm-weights/harness/ab.sh` (it compares a HEAD
archive under `.scratch/claude-20261026-night/base` with the working tree; regenerate that base with
`git archive HEAD runtime/src | tar x -C <dir>`), step trace with `harness/step_trace.py --gpu --tokens 32`, and run
all gates on both GPUs and native Windows before sealing.

## Smaller items after that (each ~1–3%, measured or estimated)

- Prefill host idle ~5 ms of a 39 ms short32 prefill: `generate()` builds the completion with 32 per-row copies
  (~1 ms, `strict_decoder_graph.py` end of `generate`; build once on CPU), `inverse = float(...item())` is a sync
  (cache the strict reciprocal per penalty value), `_session_for` validation (~0.9 ms host) could run after
  launching the exponent refresh. KV cache is zeroed at begin **and** end of each request (~0.9 ms GPU, 806 MB):
  zero only the used extent (track the maximum length; pessimistic full extent on exceptions) — keep the
  clear-on-boundary policy.
- Balanced decode split choice: pick split S minimizing `ceil(tiles*S / resident) * ceil(KT/S)` (resident = CTAs/SM
  x SMs). Operator data: down 4864x896 s7 13.3 us vs s8 14.5; QKV s5 6.2 vs s8 7.5; o s5 5.2 vs s8 5.6. Needs
  non-power-of-two split support in `integer_plan`, `_linear` checks, finishes and the workspace bound.
- Optional: L2 prefetch issued **only** where DRAM is idle without stealing SMs (all attempts so far lost).

## Scratch scripts (not evidence)

`.scratch/claude-20261026-night/`: `step_trace`-style tools, `attn_bench.py` (decode attention operator with
the short32 row-length skew), `gemm_bench.py` / `gemm_kprof.py` (decode/prefill projection operators,
`--src` for a patched copy, `EXP_DEFS` in the `src3` copy), `gemm_prof.py` (cycle counters), `imma_peak.py`,
`prefill_gaps.py`, `host_prof.py`, `lmhead_prune.py`. Copies of the useful ones are in the evidence `harness/`.
`pkill -f` matches your own shell; kill by PID. Timing needs an idle GPU.
