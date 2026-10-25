# Exact B22 raw-weight prefetch, 2026-10-26

Selected runtime source: `b1ef257a`. This continues the owner's own-kernel performance goal after the
[vLLM impact survey](../2026-10-26-vllm-impact/README.md). No vLLM execution is used in these strict timings.

The kernel overlaps the next raw FP16 tile load with current quantization/MMA, using two explicitly
aligned thread-private shared slots. It preserves B22 arithmetic and keeps one primary FP16 GPU model;
there is no persistent quantized or FP32 weight shadow. Shared scratch is 4096/8192 bytes per CTA for
four/eight warps. Automatic selection covers measured B22 SM86/SM120; explicit scalar/paired controls
remain. B14 and unmeasured architectures retain their prior automatic policy.

## Selected whole-model results

Final `*-02.json` receipts pin the selected source. Both variants share one model. The prior control
explicitly uses paired reads on SM120 and scalar reads on SM86. Eight fixed prompt strings, batches
1/8/32, context 512, 32 greedy outputs without EOS stopping, ABBA ordering and ten host-wall samples per
variant. Tokens repeat exactly and agree between variants and GPU hosts. Publication, hashing, initial
loading, compilation and capture are outside steady timings. No competing timed inference job ran on
the same host.

| Model / GPU | Batch 8 prior → selected, token/s | Gain | Batch 32 prior → selected, token/s | Gain |
| --- | ---: | ---: | ---: | ---: |
| SmolLM2-360M / 5070 Ti | 1558.3 → 1824.8 | 17.10% | 4067.0 → 4504.4 | 10.76% |
| Qwen2.5-0.5B / 5070 Ti | 1464.7 → 1865.5 | 27.37% | 3752.4 → 4346.3 | 15.83% |
| TinyLlama-1.1B / 5070 Ti | 839.8 → 1075.7 | 28.10% | 1986.7 → 2321.8 | 16.86% |
| SmolLM2-360M / 3060 | 760.4 → 861.6 | 13.31% | 1448.7 → 1567.2 | 8.18% |
| Qwen2.5-0.5B / 3060 | 654.6 → 808.6 | 23.53% | 1229.5 → 1328.0 | 8.02% |
| TinyLlama-1.1B / 3060 | 285.3 → 399.3 | 39.96% | 577.7 → 631.1 | 9.24% |

Single-row SIMT execution is unchanged; measured batch-1 ratios range from 0.9836 to 1.0355, with no
general batch-1 gain claimed. Recomputed medians, spreads and cross-host checks are in
`model-comparison-02.json`. The selected kernel remains only about 30–33% of the earlier SM120 vLLM
controls on this short workload. The near-vLLM goal is still open.

## Numerical and native acceptance

Each trained model runs eight prompts through parent, canonical seed 7001 ± sigma 0.001, and restored
parent, for both prior and selected reads. Across the two GPU hosts, schemas, input token IDs, model
files, canonical weight hashes, prefill logits, generated tokens, texts and rewards match. Each restore
is exact; serial and packed prefill agree. This is one finite candidate pair, not a learning run.

The operator suite passes 75 tests per host before the explicit shared-alignment annotation. The final
four targeted tests per host include tails, offsets, B14/B22 controls, CUDA Graph replay after live
weight change/restore, and compiled shared alignment for four/eight warps. Another 57 decoder/group/
packed/frozen-LoRA tests pass on SM120. All four scratch policy/tile/half-order mutants are killed.
The complete finite FP16 value/row-exponent quantizer test is part of the operator suite. PTX and SASS
for final scalar/paired/prefetch builds are retained for both architectures with empty audit violations.

Native Win11/3060 source `b1ef257a` passes **505 tests**, then four pinned tiny decoder layouts with
B14/B22 parent/exponent-changing/restored states and the independent CPU oracle. A trained Qwen probe
also passes parent/canonical ±/restore; its weights, tokens, texts, rewards and prefill logits equal
both Linux hosts. See `native-qwen-comparison-03.json` and native raw reports. No native throughput or
installer/managed acceptance is inferred.

Full CPU/product checks: **ALL PASS**, runtime **3158 passed / 461 skipped**, backend **452 passed**,
plus formatting, source imports, desktop/web units/types and fixture browser/Electron checks. Isolated
Linux package checks pass; Worker and notebook SDK contain all **141** matching runtime Python files,
and Server contains the expected **23** matching shared modules. `selected-source-02.json` records the
source/package hashes and unchanged approved-plan hash. Its provenance corrects inherited control-engine
metadata in `selected-source-01.json`; those old flag constants were not observations of strict processes.

## Retained experiments and failures

Prototype operator/model pilots and generic stage-2/4/8 sweeps remain. Deeper staging is not selected;
operator gains were inconsistent and did not establish better full-model throughput. Those prototype
harnesses use the unchanged runtime base `3b9c8931`; final receipts use `bench_selected.py` and the
committed runtime. `schedule-proof-01.json` checks symbolic schedules/ownership for all K tile counts
through 32768 elements and split 1/2/4/8; it is an algorithmic argument, not a compiler theorem.

Initial source-match and policy-red attempts are retained. The compiled-alignment test first found a
four-byte declaration; the final kernel explicitly declares sixteen-byte alignment. The `*-01` selected
pilots predate that annotation and are superseded by the final `*-02` measurements. Native attempt 02
stopped on a missing benchmark harness path before kernel acceptance; attempt 03 includes that path
and succeeds. No failed attempt is used as acceptance.

The owner-authorized lab status read shows services stopped. No push, merge, deployment, learning,
device-state operation or `ai` environment modification occurred. The two original worktrees are clean.

## What this does NOT show

Near-vLLM speed, general model quality, all seeds/prompts/architectures, native Windows throughput or
installer acceptance, managed kernel activation, full M0–M6 completion or learning behavior. Later
contiguous-group and 16-byte-copy prototypes have separate evidence and are not selected by this receipt.
