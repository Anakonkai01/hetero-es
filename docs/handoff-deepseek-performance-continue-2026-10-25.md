# DeepSeek continuation: strict correctness and measured performance

Owner request, 2026-10-25: give DeepSeek a more explicit continuation handoff, including actual performance
improvement and the process needed to avoid misunderstanding the goal. This supersedes the _next task_ in
[the initial handoff](handoff-deepseek-flash-2026-10-25.md); it does not replace or shrink the approved M0–M6 plan.
Codex implementation is paused. Preparing this document does not authorize Codex to resume numerical work.

**Status addendum, 2026-10-25 (after this handoff was written).** Codex continuation is now being handed over by
the owner. Audit A–D are fixed in `e03307ae` and `cc76a03d`; the first measured performance change is
`f9bfd254`. Local 5070 Ti receipts, the profile, test/mutation logs and the limits are in
`docs/evidence/2026-10-25-frozen-audit-perf/`; the living results are in
`docs/deepseek-flash-progress-2026-10-25.md`. The measured B32 gain is +22.5% on SmolLM2 and +20.5% on Qwen,
but that is still only 18–21% of the prior vLLM controls. The 3060 matrix, matched vLLM control, trained
nonzero-adapter quality/lifecycle and cross-GPU checks remain undone. Everything below still applies; do not
treat the local gain as a general or near-vLLM result.

## 1. Objective and working boundaries

The primary deliverable is a correct, portable implementation with **measured general performance improvement
toward vLLM**, across models and GPU architectures. A new artifact format, more source reading or green tests alone
does not deliver that improvement. Keep the full M0–M6 objective; a finished experiment does not finish the system.

- Work only in `/home/pc5070ti/projects/heteroes-deepseek-flash`, branch
  `work/deepseek-v4-1-flash-2026-10-25`. Verify both before editing.
- Read `AGENTS.md`, `docs/HANDOFF.md`, this handoff, the approved plan and ADR-012. Use current code and receipts
  as evidence; historical handoffs may describe an earlier implementation.
- Do not edit the Codex or Codex audit worktrees. Do not reset, clean, stash, discard or overwrite existing WIP
  merely to obtain a clean tree. Inventory it and finish or explicitly retain it.
- No push, merge, automatic cherry-pick, deployment, live device approval/contribution change or learning run.
  Keep `ai`, shared dependency/model assets, `/mnt/sekai` and Archive disks unchanged. Never store credentials.
- Existing GPU/SSH permission covers local/Nhut 5070 Ti and Thao/Quang 3060 for this task. Use
  `HETEROES_GPU_ACCEPTANCE=1`, plus `--gpu` where supported. Do not ask for the same authorization again.
- Only the DeepSeek worktree's own `.scratch/` is writable experimental space. Shared model/dependency links
  are for reading. Create fresh remote stages and receipt names. Check free disk before creating model artifacts.

## 2. Actual starting state, not the original starting assignment

At this handoff's inspection, the DeepSeek branch HEAD was `6299f62e`:

- `79681d88`: pinned source review of vLLM/SGLang/TensorRT-LLM.
- `e0b1d57c`, `3ed26c68`: frozen-int8 artifact/oracle and its initial receipts.
- `39aefba9`, `f4ef2884`: content addressing and typed frozen-base/FP16-LoRA storage.
- `b8648792`, `fe7c472b`: three-limb CUDA projection and captured decoder integration.
- `6299f62e`: integration receipts and remaining gates.

There were also uncommitted changes in `frozen_int8_decoder.py`, `strict_decoder.py`,
`model/frozen_int8.py` and their tests, plus untracked `fp16_decoder.py` and its CUDA test. Re-read status and the
diff because this inventory is a checkpoint, not a claim that those files stopped changing.

`docs/deepseek-flash-progress-2026-10-25.md` reports 53 initial oracle tests, 3116 CPU runtime passes/426 skips,
31 local CUDA operator/graph passes and mutation receipts. These are **reported trial results**, not full Codex
acceptance. They do not prove cross-GPU strictness, trained-model speed, general quality or M6 completion.
The progress note explicitly has no trained-model throughput measurement and no measured speed improvement.

The accepted comparison baseline remains numerical source `3fd704a5`, with acceptance at `ced64601` and later
test/experiment coverage at `253ebb98`. It remains experimental; the current recipe/default is unchanged.
Use [the existing performance comparison](strict-vllm-comparison-2026-10-25.md) for complete workload/environment scope.

| Model          | B22 B1 | B22 B8 | B22 B32 | Prior vLLM default B32 |
| -------------- | -----: | -----: | ------: | ---------------------: |
| SmolLM2-360M   |  277.3 | 1493.9 |  3861.3 |                14429.4 |
| TinyLlama-1.1B |  187.5 |  783.9 |  1804.6 |                 7791.8 |
| Qwen2.5-0.5B   |  277.5 | 1386.4 |  3470.5 |                13802.5 |

These are total output tokens/s on local 5070 Ti, fixed B1/B8/B32, greedy 32 output tokens, context 512,
EOS stopping/prefix reuse off, one warmup and median three synchronized wall measurements. The vLLM measurements
are from separate prior stages/builds on an unisolated GPU. They are orientation data; use fresh matched controls
to establish a new improvement. B32 is about 23–27% of default vLLM; the near-vLLM goal is not met.

## 3. First: resolve the audit issues before building speed claims

Codex did a limited CPU audit of a captured unfinished source, not a complete audit of the current branch. Six
checks reproduced problems while all 53 supplied initial tests passed. The record and exact source hashes are at
`/home/pc5070ti/projects/heteroes/.scratch/deepseek-audit-20261025-01/`:
`source-snapshot.json`, `reproduced-findings-01.json`, and `reproduce_findings_inference.py`.
Read these as historical repro evidence. Port the cases into tests of the current source; the helper's original
working-directory/output paths are not a ready-made command for this worktree. Do not modify those receipts.

### A. RNE overflow boundary is wrong in the CPU encoder and its test oracle

`encode_scaled_integer_bits` rejects every exact value above max-finite. FP32 RNE must instead round values below
the overflow midpoint back to max-finite. The initial test helper `float_bits` contains the same wrong guard, so
its apparent independence misses the defect. The current inspected source still contains both guards.

Add tests **before fixing code**, for both signs:

```
integer = (((1 << 24) - 1) << 2) + 1
exponent = 102
expected positive FP32 bits = 0x7f7fffff
expected negative FP32 bits = 0xff7fffff
```

This exact magnitude is `max_finite + 2^102`, below the RNE overflow midpoint
`max_finite + 2^103 = 2^128 - 2^103`. At that midpoint, RNE does overflow. Cover below/at/above the midpoint,
mantissa carry, min-normal rounding and signed FTZ with an independent rational/bit-search oracle.

The failure is reachable through a quantized artifact and `linear`, not only a direct encoder helper:

```
source FP32 weights = [[1.0, 2^-6, 127/64 - 2^-23]]
quantized weights   = [[64, 1, 127]]
stored scale bits  = 0x3c7fffff
input FP32         = [[max_finite, 2^106, 0.0]]
B22 activation q   = [[2^22, 1, 0]], exponent 127
expected output    = 0x7f7fffff
```

Reproduce on the current CPU and CUDA implementations. Do not force CUDA to match a faulty CPU oracle.
Keep the artifact/CPU/CUDA rounding contract consistent and preserve the original failing receipt.

### B. Verified/frozen payload admission needs an actual invariant

The captured public dataclass was writable through its tensor contents under `torch.inference_mode()`.
Changing `weight_q` changed output without changing `sha256`; a negative scale then passed `linear`, and a
directly constructed object with int64 weights and format version 999 was also accepted as "verified".

Recheck the current typed module/reader/decoder paths and add tests for in-place edits, buffer replacement,
metadata edits and forged/unverified objects. Define ownership and admission so that an invalid frozen payload
is rejected before arithmetic or used only under a newly verified identity. Construction-time hashing alone
does not justify treating mutable storage as immutable forever. Preserve bounded memory and avoid hashing a
whole model on every decode token; choose and explain a lifecycle check that enforces the invariant.

### C. Nonzero LoRA must follow a portable strict operator contract

At the inspected trial, `lora_delta` uses ordinary FP32 `torch.matmul`, and `combine_adapter` uses ordinary
addition. Its own namespace explicitly declines cross-GPU equality. That is an acknowledged limitation, but
does **not** satisfy M6's requirement that the base, adapters and combination obey the strict execution contract.
Zero-initialized B and zero-delta tests cannot establish correctness for actual perturbed adapters.

Specify/reference/test both adapter matrix products, scale and final add, including rounding/FTZ/contraction and
nonfinite failure behavior. Reuse proved strict kernels where appropriate. Pin scaling bits and identity.
Test nonzero A and B, canonical plus/minus perturbations, update/replay primitives and exact restore across GPUs.
A new fingerprint does not make an ordinary vendor matmul portable. Do not weaken the goal by moving the
trainable part outside the strict contract and declaring the frozen base alone sufficient.

### D. Check CUDA arithmetic assumptions and the new WIP paths

- The inspected `frozen_linear` reconstructs negative signed limb accumulators with signed left shifts.
  Avoid relying on undefined C++ behavior; use a defined, bounded signed-integer formulation and test cancellation,
  negative limbs, endpoints and split reductions. PTX/SASS audits must refer to the resulting source.
- Nonoverflowing exact integer sums may change partition/order without changing their value. Batch invariance
  requires identical results, not identical launch geometry. Keep safe dimension/SM-based scheduling available;
  do not impose an unnecessary ban on exact split-K to imitate a floating reduction restriction.
- Inspect the untracked `fp16_decoder.py` before retaining or using it. A fast ordinary-FP16 baseline is useful
  when explicitly labelled; it cannot silently become the strict path or supply its speed claim.
- If WIP introduces a tied-head int8 sidecar, check actual computation, aliasing and memory, not just metadata.
  An FP16 embedding and a separately approximated int8 head are not proof of the same tied numerical weight.
  Preserve the declared tie/storage semantics, or reject/version a changed supported configuration explicitly.
- Retain the exact frozen-base artifact identity. Do not create a full dequantized FP16/FP32 base shadow or
  hide a full second weight representation behind a `.weight` property, cache or export/validation path.

## 4. Then produce measured performance progress

After the correctness/admission blockers above are covered, continue implementation rather than stopping at
the format or fixture gate. The next deliverable must include a reproducible trained-model timing comparison
and a profile that determines the next optimization. If a candidate is slower, preserve/reject it and continue
from the measured bottleneck; do not report it as a performance improvement.

1. **Pin and load the real model artifacts.** Use the existing local SmolLM2, TinyLlama and Qwen assets. Record
   complete consumed-file manifests, quantized base/adapter hashes, format/config/backend identities and prompts.
   Quantize once into a pinned artifact, then load the same bytes on each GPU. Record load/quantization cost
   separately. Keep only one full primary inference weight set on the GPU, including validation/export reload.
2. **Measure the whole supported path.** Include nonzero adapters, prefill and captured decode, plus the exact
   base and adapter operator times. Record load, candidate entry, perturb, inference, restore and reload peaks.
   A fast base kernel with a slow/nonportable adapter path is not the finished M6 result.
3. **Profile before the next kernel change.** Prior B22 B32 profiles put 66–84% of CUDA event time in projection.
   Measure the new format instead of assuming that percentage remains true. Separate conversion/packing,
   base MMA, 96-bit encoding, adapters, attention, copies and host/launch/capture overhead. Event sums are not wall shares.
4. **Implement and compare the next bottleneck fix.** State the hypothesis and affected dimensions first.
   Candidates include primary weight layout/vector loads, reuse across output/row tiles, register/occupancy
   tuning, exact split-K, grouped projections and legal fusion. Use model-independent dimension/hardware rules.
   No Qwen-name branch, hidden precision reduction, unsupported-op fallback or special-case prompt shortcut.
5. **Keep iterating toward vLLM.** Three limb products instead of nine is a work-count reduction, not a claim
   of 3x speed. Report the achieved ratio to vLLM and the remaining gap. No new fixed percentage target has been
   approved; do not quietly redefine "near vLLM" to mean that a test or one favorable benchmark passed.

Same-B22 scheduling optimizations and quantized-base/LoRA experiments are different comparisons. The latter
changes the model/search space: label its accuracy and storage tradeoff and do not present it as an unchanged
full-weight FP16-ES speedup. Keep the original B22 and historical FP32 references intact.

## 5. Benchmark and quality procedure

- Minimum trained matrix: **SmolLM2-360M, TinyLlama-1.1B, Qwen2.5-0.5B**, local 5070 Ti and at least one 3060,
  B1/B8/B32. Report every case, including regressions and failed/unavailable cases.
- Use the same prompt token IDs and output-token budget across engines. For the existing workload: greedy,
  32 new tokens, max context 512, EOS stopping and prefix reuse off, the fixed eight-prompt pool. B1 uses the
  first prompt, B8 each once and B32 four repeats. Pin tokenizer/model revisions and runtime versions.
- Exclude compilation/capture/warmup from warmed throughput and report cold cost separately. Use synchronized
  host wall time, at least one warmup and at least five timed observations for new claims. Save raw timings,
  median and spread; an effect inside run variation is not established improvement.
- For kernel variants of the same arithmetic/storage, prefer paired ABBA with one primary model and explicit
  compiled-module routing. For different model representations, use controlled sequential loads/processes;
  do not retain a second complete GPU weight set merely to make the benchmark convenient.
- Do not overlap timed probes on the same GPU. Record environment/load limitations. Recheck a claimed gain on
  the other architecture; a faster 5070 Ti case does not prove a faster 3060 case.
- Keep vLLM default and batch-invariant results separate. Neither label supplies our heterogeneous strict proof.
  Refresh matched engine measurements when needed; do not compare a fresh best case with an unmatched old workload.
- Keep FP16-vs-int8 quality differences separate from same-contract correctness. Use a pinned finite evaluation
  corpus/scorer, report the actual quality/logit/token/reward differences and limitations; do not infer quality
  from three short generations. No learning run is authorized.
- For the new strict identity, compare parent and **nonzero canonical ± adapters**, batching/permutation,
  prefill/decode/cache and restored output across GPUs. Exact adapter/parent restore and artifact hashes are
  required. Finite update/replay/restore primitive tests are allowed; they are not training experiments.

## 6. Tests, evidence and final review sequence

Run independent targeted tests before new behavior, then scratch mutation checks. A surviving mutant needs a
new discriminating test or a documented equivalence. Do not copy a production shortcut into the oracle. Cover
odd K/N/M, alignment/offsets/tails, endpoints, cancellation, signed zero, FTZ/min-normal/overflow, invalid inputs,
rebind/in-place changes, capture/release, failures and memory bounds at the scope affected by the change.

Runtime CPU checks need the numerical environment, not the backend-only venv (which has no Torch):

```bash
cd /home/pc5070ti/projects/heteroes-deepseek-flash
PY_RUNTIME=/home/pc5070ti/miniforge3/envs/heteroes-match/bin/python
CUDA_VISIBLE_DEVICES='' PYTHONPATH=runtime/src "$PY_RUNTIME" -m pytest runtime/tests/eval/test_frozen_int8.py runtime/tests/model/test_frozen_int8_storage.py -q
HETEROES_GPU_ACCEPTANCE=1 PYTHONPATH=runtime/src "$PY_RUNTIME" -m pytest runtime/tests/eval/test_frozen_int8_cuda.py runtime/tests/eval/test_frozen_int8_decoder_cuda.py -q
```

Adapt commands for newly added tests. For a selected reviewable source, finish required CPU/backend checks,
check-all and fresh Linux packaging, then hardware/native acceptance at its actual claimed scope. Recheck the
resulting source/package hashes. Native fixture passes are not native trained-model/installer acceptance.
Do not repeat the full suite for each rejected scratch prototype when targeted checks suffice.

Each experiment gets fresh output paths under a dated evidence folder with a README containing
**What this does NOT show**. Record commit, dirty-source hash if any, model/backend/adapter identities, exact
commands, raw JSON/logs, rejected variants, mutation results, resource peaks, PTX/SASS audit availability and
counterexamples. Preserve existing receipts byte-for-byte; do not format evidence/generated files.

Commit logical groups only after reviewing the staged diff. Do not accidentally include unrelated WIP in a
documentation or receipt commit. Update the progress note with separate **proposed / implemented / tested /
selected / unaccepted** states. No automatic integration into the Codex branch.

## 7. Required continuation deliverables

Leave a concrete result Codex can audit:

1. Fixes and independent regressions for the reproduced rounding/admission issues, plus the current LoRA
   strictness and CUDA arithmetic decisions, with precise changed identities.
2. The actual implementation and trained-model artifact identities, with bounded physical storage and no hidden shadow.
3. A table for all model/GPU/batch cases: baseline throughput, new throughput, ratio, raw timing spread, memory
   and quality/correctness status. Distinguish improved, unchanged/noisy, regressed, failed and unmeasured.
4. A profile-backed optimization decision: what changed, why it helps, where it fails, and the next bottleneck.
   If no general improvement was established, say so and keep the objective open rather than calling the format fast.
5. Exact local commits, reproducible commands/receipts, remaining gate inventory and any live job/session handles
   in `docs/deepseek-flash-progress-2026-10-25.md`. Verify process state before restarting an apparently stalled job.

M1/M2 are not complete. D10/D11 recovery/watchdogs, M3 storage/replacement, M4 ownership/qualification/native
delivery, M5 system acceptance and M6's full lifecycle remain required. Audit UI/docs are not a substitute for the
current performance/kernel priority. Keep `hardwareQualified: false` and managed strict/default inactive until
the real gates are met. Codex will independently audit the actual final source, tests, mutations and measurements.

The approved plan must retain SHA-256
`4ee6838fa47f810ee40348b5f0bc556834bf50825eb0b7b0795b5053743cb17f`.
Frozen noise/ES/ledger/generation-record behavior and historical replay identities remain unchanged.
