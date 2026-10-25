# HeteroES candidate execution through vLLM, 2026-10-25–26

Selected source: `c9a37059fca1d16b142df421a19cebcde0f7cd39`, following the live FP16 merge fix
`3735d6db`. The owner explicitly reprioritized near-vLLM performance and permitted alternative arithmetic.
This experiment uses **vLLM as the inference backend** while HeteroES publishes canonical ES candidates
and restores their weights. It is a standalone candidate/inference probe, not a managed worker activation.

## Matched inference performance

Same pinned model/tokenizer files and token IDs, eight canned prompts repeated to batches 1/8/32,
greedy 32 output tokens, context 512, prefix caching off, one warmup and five timed observations.
The controls and ES probes run in separate processes with matching configuration, rather than ABBA.
Both explicitly use `VLLM_USE_FLASHINFER_SAMPLER=0` and single-process vLLM 0.32.0. This avoids the
FlashInfer sampling JIT failure preserved in the preceding evidence; it is not an unmodified-default
sampler claim. All reference and ES parent token streams match within each host.

Batch 32, median total output tokens/s:

| Model | 5070 Ti vLLM control | HeteroES/vLLM | Ratio | 3060 vLLM control | HeteroES/vLLM | Ratio |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SmolLM2-360M | 14487.4 | 14414.6 | 99.50% | 5439.6 | 5478.5 | 100.71% |
| Qwen2.5-0.5B | 13834.6 | 13813.2 | 99.85% | 4868.1 | 4855.4 | 99.74% |
| TinyLlama-1.1B | 7769.1 | 7761.0 | 99.90% | 2433.8 | 2426.7 | 99.71% |

Ratios around 100% reflect ordinary timing variation. The inference implementation is the same engine.
These generation timings include prefill and host generation overhead, but **exclude candidate publication,
CPU snapshot/weight-hash audits and initial model loading**. They are not total ES-generation throughput.
Publication/restore timings are reported separately, including the first canonical CUDA warmup: local
plus/minus approximately 0.18–1.02 s in this finite run. Audit and CPU-snapshot overhead is not hidden in an
inference ratio. Longer candidate workloads and update/lifecycle throughput remain separate measurements.

## Candidate identity, sharing and inference differences

`hf_parameter_view` constructs only a meta HF template, then exposes canonical parameter names/order,
shapes and ties as views of vLLM's fused QKV/gate-up storage. No second GPU model is loaded. Every ES view
storage is verified to belong to the serving owner; the snapshot is on CPU. Public `LLM.apply_model`
publishes weights in place, then generation runs with fresh request KV and disabled/reset prefix caching.
The view module has no inference forward implementation. The final exact restore runs after probe errors too.

For all three models and both hosts, schema, parent and seed-7001/sigma-1e-3 canonical plus/minus weight
hashes match the earlier full-weight B22 receipts. Parent/restored output streams match exactly on each
host. The noise/ES/ledger recipes were unchanged; vendor inference has its own experimental identity.

Cross-host token agreement over parent/plus/minus/restored and all three batches:

| Model | Equal 32-token rows | Equal scorable numeric rewards |
| --- | ---: | ---: |
| SmolLM2-360M | 163 / 164 | 104 / 104 |
| Qwen2.5-0.5B | 164 / 164 | 104 / 104 |
| TinyLlama-1.1B | 164 / 164 | 104 / 104 |

Smol's plus/batch-8 case differs in one row and nine token positions on SM120; B22 and SM86 agree there.
The canned numeric reward for that row is unchanged. Unscored prompts are excluded from the numeric reward
denominator in [comparison 02](model-comparison-02.json); comparison 01 also counted equal null reward slots
and is preserved. Most rewards are zero, so reward agreement here is weak evidence of quality. Eight prompts
repeated across batches are a finite sensitivity corpus, not 164 independent questions or a benchmark suite.

## Intermediate FP16 control and verification

The older experimental FP16 graph copied merged weights once and missed subsequent ES writes. The new
v2 graph binds original Parameter objects into live merged allocations, preserves aliases with a per-module
fallback, and rebuilds groups after storage replacement. Its batch-32 local ABBA result is 7179.9/7848.1/
4851.9 tokens/s for Smol/Qwen/Tiny, versus selected B22 4067.7/3757.7/1986.0. This intermediate backend retains
strict nonlinears; its result is distinct from the vLLM backend table. Those intermediate raw identities pin the snapshot before the final empty-group rejection guard; final targeted tests include that guard.

Seventeen targeted view/storage/FP16 tests passed on each GPU host. Three parameter-view mutants and one
stale-merge mutant were killed on scratch copies. Initial red tests, the failed fixture-bias assumption
in view-green attempt 01 and corrected nine-test attempt 02 are retained. An independent comparer validates
canonical hashes, shared storage assertions, restore streams, reference tokens and recomputed timing medians;
vendor cross-GPU differences are measured rather than converted into a false equality claim.

`check-all-03/` completed **ALL PASS**: runtime CPU 3158 passed/459 skipped and backend 452 passed, plus the full product checks. The isolated Linux package check
passed at the selected source, with Worker/Server shared-module imports. Source audit verifies all 141 runtime
Python files in the Worker archive and Server notebook SDK, plus the Server's intended 23-file shared subset.
This is package/import acceptance, not execution of vLLM inside an installed managed Worker. Existing shared
environment dependencies, profiles and live services were not replaced. The earlier B22 check attempt 02
was incomplete after a host restart; it supplies no acceptance claim.

`selected-source-01.json` pins matching runtime files on the remote host, the actual installed vendor source
files, compiler/sampler settings, package contents and unchanged approved-plan digest. Harnesses and complete
raw streams/timings are retained. The source architecture rationale is in
[`runtime/docs/vllm-es-parameter-view.md`](../../../runtime/docs/vllm-es-parameter-view.md).

## What this does NOT show

No claim that the custom B22 kernel reaches vLLM speed, no bit-exact vendor inference guarantee, broad model
quality, learning result, native Windows trained/installer acceptance, managed candidate lifecycle, device
qualification or production rollout. vLLM remains an optional separately installed inference dependency;
the base Worker does not silently select it. `hardwareQualified` is false. No push, merge, deployment,
device-state change, historical recipe edit or shared-environment installation.
