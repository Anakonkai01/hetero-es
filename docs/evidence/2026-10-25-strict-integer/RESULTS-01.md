# Integer feasibility results — selected source `fb18a7b7`

The full approved M0–M6 objective remains active and incomplete. This checkpoint implements a *new* arithmetic
reference and optional decoder. It does not activate strict in a managed recipe. No push, merge, deployment,
device-state change, learning run, sudo operation or change to the `ai` environment was performed.

## Implemented baseline

- CPU reference: row-local power-of-two scales, exact ties-even integer quantization (B14/B22), bounded integer dot,
  exact scaled-integer FP32 RNE encoding followed by signed FTZ, existing rounded bias add. Rational test oracles
  avoid binary64 double rounding. The previous FP32-tree arithmetic and frozen noise/ES/ledger files are preserved.
- CUDA: signed int8 MMA with balanced radix digits, grouped degree accumulators, exact int64 reconstruction,
  optional bounded split-K, SIMT for a single row, no materialized full quantized/FP32 weight copy. Compiler audits
  require signed MMA/IMMA and reject floating dot/multiply. A module containing MMA does not mean B1 uses MMA.
- Graph adapter: same restricted shared Qwen2/Llama/Mistral graph and strict nonlinearities. Weight exponents are
  refreshed once per locked request from live FP16 weights, checked before prefill, cleared before unlock. Binding,
  stream and capacity invalidation retain the original graph lifecycle. Noncached/failure paths clear metadata too.
- `benchmark_inference.py --engine strict-integer --integer-bits 22` and `probe_integer_decoder.py` are explicit
  experimental tools. The new reference/decoder/source fingerprints never assert FP32-tree equivalence.

The [contract](../../../runtime/docs/integer-projection-v1.md) contains the operation sequence and nonoverflow proof.
The evidence source files in this directory are historical prototypes, **not** imports used by the selected backend.

## Verification

| Receipt | Result and scope |
| --- | --- |
| `check-all-01.log`, `checks-01/` | **ALL PASS**: 3016 runtime CPU passed / 285 skipped; 452 backend passed, existing deprecation warning. Lint/format, source imports, units/types/i18n, fixture browser/Electron checks pass. |
| `gpu-nhan-06.log`, `gpu-{nhut,thao,quang}-02.log` | **301 selected tests passed on each target**: local/Nhut 5070 Ti (Linux), Thao/Quang 3060 (WSL2). Includes independent CPU rational answers, physical projection midpoint/overflow boundaries, odd widths/tails, execution variants and legacy strict regression. |
| `metadata-decoder-nhan-03.log` | 41 passed: four layouts × two precisions, CPU oracle logits/tokens, live exponent-changing weights, reuse/clear/rebind/error/noncached request semantics, old graph and benchmark guards. |
| `mutation-cpu-01.log`, `mutation-gpu-01.log` | **11/11 killed** on scratch copies: ties, FTZ boundary, row independence, carries, bias, degree reconstruction, split overlap, live metadata refresh/nonfinite flag. Control runs pass. |
| `linux-package-01.log`, `source-package-identity-01.json` | Linux source-copy apps pass. Five runtime files match the packaged Worker source and Server's embedded SDK wheel. Build metadata records starting HEAD `abe40dd9`; explicit file hashes cover the subsequently committed implementation. Not native Windows/GPU package acceptance. |
| `lab-status-01.log` | Deployed lab remains `82c37fc`; all three services stopped. Read only. |

Red and intermediate receipts remain intact, including test-harness corrections. No passing retry overwrites its failure.

## Controlled trained parent throughput

Same eight prompt token lists, 32 output tokens, context limit 512, FP16 storage, EOS/prefix caching disabled, excluded
warmup and median of three synchronized host measurements. B32 repeats the eight prompts four times. Timings include
prefill, request metadata refresh, graph replay and host overhead. `bench-*-nhan-02.json` is the selected baseline;
the earlier Smol `*-01` uses context 128 and is excluded from this controlled comparison.

| Model / GPU | B22 B1 | B22 B8 | B22 B32 | Prior FP32 B32 | Prior vLLM default B32 |
| --- | ---: | ---: | ---: | ---: | ---: |
| SmolLM2-360M / 5070 Ti | 177.1 | 434.3 | 1318.2 | 804.9 | 14429.4 |
| TinyLlama-1.1B / 5070 Ti | 114.5 | 299.4 | 830.7 | 288.8 | 7791.8 |
| Qwen2.5-0.5B / 5070 Ti | 171.8 | 465.1 | 1358.5 | 500.7 | 13802.5 |
| SmolLM2-360M / Thao 3060 | 109.4 | 291.1 | 663.6 | 211.6 | not measured in this stage |
| Qwen2.5-0.5B / Thao 3060 | 108.0 | 287.9 | 613.1 | 157.7 | not measured in this stage |

Units are total generated tokens/s. B22 B32 improves 1.64–2.88x on 5070 Ti, but reaches only 9–11% of prior vLLM
default. B1 regresses to 74–86% of prior FP32. B14 is not consistently faster: local B32 Smol/Tiny/Qwen is
1236.4/789.8/1325.5. All selected repeat and batch-vs-single token comparisons pass in these receipts.

`trained-comparison-01.json` asserts workload/prompt/consumed-asset equality and records the exact prior receipt paths.
vLLM has a separate Torch/CUDA/Transformers environment; GPUs are unisolated and runs are sequential measurement
stages. Prior Smol full manifests include HF download metadata, explicitly excluded **only** from consumed-asset
comparison. `fullManifestEqual:false` remains visible. New asset-only hardlink inputs preserve original files/history;
their full manifests match the two trained cross-GPU probe inputs. See `model-assets-01.json`.

## Trained canonical candidates and counterexample

`quality-{smol,tiny,qwen}-nhan-01.json`: parent, canonical v2 seed 7001 at ±sigma 1e-3, then restored parent; eight
prompts, 32 output tokens each. All engines share the original FP16 model. A CPU parent snapshot supports the frozen
exact-restore implementation. Every state restores to the initial weight hash; restored prefill logits and tokens
also match the initial parent. Candidate effects remain visible in both logits and token streams.

B22 matches the old FP32-tree token streams on all these finite states. Its relative prefill RMS error spans roughly
6.8e-6 to 2.1e-5. B14 relative RMS error is roughly 0.0015–0.0056 and **one Qwen minus-candidate stream differs**.
That counterexample is retained in full, including first differing token position. Neither reference agreement nor
agreement on these short generations establishes model quality or an all-input FP32-tree equivalence.

`quality-{smol,qwen}-thao-01.json` repeats the same source/assets/noise/schema and weight hashes on 3060. For parent,
plus, minus and restored states, prefill logit hashes, complete tokens, decoded text and canned rewards match 5070 Ti
for FP32, B14 and B22. `trained-comparison-01.json` asserts each field separately. TinyLlama trained cross-GPU
acceptance is still open; four-GPU small-layout tests are separate evidence.

## Performance hypotheses retained separately

- `linear-*-01`, `split-nhan-02/03`: synthetic matrices, sampled CPU reference and full execution-variant bit
  comparisons. B32 best geometry is around 4–5x the FP32 operator on surveyed shapes. CUDA event timings exclude
  host overhead and do not establish model throughput. Split-K remains explicit rather than a trained auto policy.
- `source-vector-01.py`, `linear-nhan-02`: aligned vector-load attempt passed unaligned fallback tests but regressed
  enough cases to be rejected. Selected source uses scalar tile reads.
- `split-nhan-01`: runtime split stride produced compiler-generated float reciprocal control code; audit rejected it.
  Selected source uses a compile-time stride. This is not an accepted float fallback.
- `source-cvt-prototype-01.py`, `source-cvt-audit-01.py`: **unselected scratch variant**, exact exponent-bit scaling
  followed by PTX `cvt.rni.s32.f32`; no floating multiply. `probe-half-quant-03.py` checks every admitted finite FP16
  value/row-exponent combination: 1,017,852 pairs per precision per target. Baseline and variant pass on Nhut and Thao;
  the first two Nhut receipts retain context/argument mistakes in the harness. `cvt-nhut-03.log` records 99 passing
  operator/decoder tests, then controlled baseline/variant sweeps. `cvt-comparison-01.json` shows ~1.2–1.6x B1 operator
  improvement on 5070 Ti, with smaller and shape-dependent B32 improvement. Trained scratch measurements have distinct
  `bench-cvt-*` and `quality-cvt-*` names and are not the selected-source results in the table above.

## What this does NOT show

No near-vLLM performance, universal heterogeneous guarantee, general model quality, native Windows acceptance,
managed recipe/qualification/role ownership, failure/replacement lifecycle acceptance, learning result or completion
of M1/M2/full M0–M6. All identities retain `hardwareQualified:false`. Lower precision, hardware peaks and a passing
finite corpus are insufficient grounds to weaken the arithmetic or promote a default.
