# Frozen-int8 strict decode: fused adapter finish and measured throughput

Date: 2026-10-25. Branch: `work/deepseek-v4-1-flash-2026-10-25`. Plan SHA-256:
`4ee6838fa47f810ee40348b5f0bc556834bf50825eb0b7b0795b5053743cb17f`.

This folder records the first performance change after the frozen-int8 audit fixes. The performance source is
commit `f9bfd254` ("Fuse the strict LoRA finish and tile the first adapter product") on top of `cc76a03d`. The
zero-B receipts in `raw/pre-fix/` are earlier `cc76a03d` runs preserved byte-for-byte from
`.scratch/bench-local/20261025-recheck/`; the `pre-fix-*` nonzero-B controls were re-run from a `git archive` of
`cc76a03d`.

## What changed

Two changes, both in the strict adapter epilogue. Neither changes the base integer projection, the FP16
baseline, or the CPU reference contract.

1. The first rank product `linear(value, A)` now runs with `row_tile=1`. At rank 8 the default row tile
   serialises several rows through one block while sharing the widened weight registers; one row per block is
   faster and is scheduling-only. A dedicated test asserts `row_tile` never changes one result bit.
2. `strict_lora_finish` fuses the second rank product `middle @ B^T`, the strict scalar scale, the zero-delta
   select and the strict add. It keeps the same one-lane-per-element xor tree as `strict_linear` at this width,
   then uses a shared-memory epilogue so base reads and output writes are coalesced. The old path materialised
   `delta`, then `scaled`, then `added`, then selected with `torch.where`.

The strict arithmetic is unchanged: `ops.linear` twice, strict scalar multiply, and the zero-delta-preserving
strict add. The fused kernel must return the same bits as that sequence; the decoder still uses the exact frozen
base path. `strict_lora_finish` rejects rank > 32, non-finite factors and non-finite inputs through the same
error flag as the other captured kernels.

## Workload and environment

- Host: local `5070ti`, NVIDIA GeForce RTX 5070 Ti, Linux 7.0.0-38-generic, PyTorch `2.13.0+cu132`,
  CUDA `13.2`.
- Models: local SmolLM2-360M (`LlamaForCausalLM`), TinyLlama-1.1B (`LlamaForCausalLM`), Qwen2.5-0.5B
  (`Qwen2ForCausalLM`), loaded from `.scratch/strict-integer-20261025/models/{smol,tiny,qwen}`. File SHA-256
  manifests, config architecture fields and the exact per-model prompt token IDs are in
  `model-manifests.json`. The prompt digests match the `promptDigest` in every receipt.
- Workload: eight fixed prompts, greedy, 32 new tokens, maximum context 512, EOS stopping off, prefix cache
  off. B1 uses prompt 0, B8 uses each prompt once, B32 repeats the eight prompts four times. One warmup per
  batch size, then five timed observations. Timings are synchronised host wall time around a warmed, captured
  `generate`; compilation, capture and the warmup are excluded.
- Adapters: rank 8, alpha 16, scaling 2.0, deterministic seed 1234. The constructor follows PEFT: A is
  Kaiming-uniform and B is zero. The "zero-B" matrix below is that default. The "nonzero-B" matrix fills every
  `lora_B` from a fixed CPU generator with normal(0, 0.02), then runs the same workload. That fill is a
  throughput probe only; it is not an ES canonical perturbation and is not a quality evaluation.
- `--decode-target 8` (the default) is used everywhere.

`raw/` holds the zero-B matrix. `raw/nonzero-adapter/` holds the nonzero-B probe and the two pre-fix
nonzero-B controls. Every JSON has the five raw durations, median, milliseconds/step, tokens/s, deterministic
repeat equality and allocator peak.

## Results on the 5070 Ti

The cell format is median tokens/s (observed min–max spread as a percentage of the median). Peak memory is the
CUDA allocator peak in MiB at B1/B8/B32; it is cumulative over earlier rows, not process RSS. `equal=true`
means the full generated token lists were identical across the five timed repeats.

### Zero-B default matrix

| Model / engine | B1 | B8 | B32 | Peak MiB B1/B8/B32 | Fingerprint |
| --- | ---: | ---: | ---: | ---: | --- |
| SmolLM2 frozen head | 152.5 (0.9%) | 1101.4 (1.0%) | 3077.7 (0.2%) | 488/812/1892 | `3b4b310329e8c92c` |
| SmolLM2 frozen no head | 149.1 (0.7%) | 1021.0 (1.1%) | 2446.1 (0.4%) | 442/766/1846 | `a286c996dcb39581` |
| SmolLM2 FP16 baseline | 365.2 (1.2%) | 2229.4 (1.5%) | 7195.2 (0.8%) | 1204/1521/2605 | `98f3ccf52e431241` |
| Qwen2.5-0.5B frozen head | 181.2 (0.8%) | 1215.8 (0.5%) | 2907.5 (0.4%) | 756/881/1300 | `30b8befebf19305f` |
| Qwen2.5-0.5B frozen no head | 166.2 (1.0%) | 900.0 (0.7%) | 1521.4 (0.2%) | 626/751/1169 | `5ffd19e006dffc78` |
| Qwen2.5-0.5B FP16 baseline | 382.7 (1.3%) | 2477.7 (1.2%) | 7849.2 (0.5%) | 1475/1597/2009 | `76f9dca3eff095ff` |
| TinyLlama-1.1B frozen no head | 149.3 (0.6%) | 785.9 (0.3%) | 1437.3 (0.1%) | 1237/1445/2150 | `c00f448ca3def157` |
| TinyLlama-1.1B B22 | 187.2 (0.4%) | 786.4 (0.2%) | 1810.5 (0.3%) | 2126/2328/3002 | `210e81462cc87b56` |
| TinyLlama-1.1B FP16 baseline | 270.9 (1.0%) | 1655.3 (0.8%) | 4858.5 (0.6%) | 3377/3583/4274 | `ccaff6840ece1c36` |

TinyLlama frozen head is unavailable: `freeze_tied_head` raises `ReferenceArithmeticError("A frozen sidecar
head requires the tied FP16 LM head")` because this checkpoint has an untied LM head. No substitute is reported.

### Nonzero-B probe (adapter add path exercised)

| Model / engine | B1 | B8 | B32 | Peak MiB B1/B8/B32 | Fingerprint |
| --- | ---: | ---: | ---: | ---: | --- |
| SmolLM2 frozen head | 153.1 (0.6%) | 1097.9 (0.9%) | 3082.9 (0.4%) | 488/812/1892 | `3b4b310329e8c92c` |
| SmolLM2 frozen no head | 148.7 (0.6%) | 1018.5 (0.9%) | 2444.9 (0.2%) | 442/766/1846 | `a286c996dcb39581` |
| Qwen2.5-0.5B frozen head | 181.7 (1.5%) | 1219.5 (0.6%) | 2908.3 (0.4%) | 756/881/1300 | `30b8befebf19305f` |
| Qwen2.5-0.5B frozen no head | 165.9 (1.0%) | 897.1 (0.5%) | 1519.7 (0.2%) | 626/751/1169 | `5ffd19e006dffc78` |
| TinyLlama-1.1B frozen no head | 149.8 (0.6%) | 786.2 (0.4%) | 1436.0 (0.2%) | 1237/1445/2150 | `c00f448ca3def157` |

The nonzero-B probe is within run noise of the zero-B matrix (largest B32 difference 0.2%), as expected for
the same work count with no value-dependent shortcuts. It shows the add path is not slower; it does not make
the adapters trained or meaningful.

### Before vs after on the primary path

| Case | Five-run median tok/s | Change |
| --- | ---: | ---: |
| SmolLM2 frozen head B8, pre-fix | 888.5 | — |
| SmolLM2 frozen head B8, after | 1101.4 | +24.0% |
| SmolLM2 frozen head B32, pre-fix | 2511.8 | — |
| SmolLM2 frozen head B32, row-tile only | 2870.7 | +14.3% |
| SmolLM2 frozen head B32, after | 3077.7 | +22.5% |
| Qwen frozen head B8, pre-fix | 974.2 | — |
| Qwen frozen head B8, after | 1215.8 | +24.8% |
| Qwen frozen head B32, pre-fix | 2413.2 | — |
| Qwen frozen head B32, after | 2907.5 | +20.5% |

B1 is unchanged: SmolLM2 153.6 → 152.5 (−0.7%, inside the 0.9% spread) and Qwen 181.3 → 181.2 (0.0%). The
nonzero-B controls agree: SmolLM2 B32 2516.6 → 3082.9 (+22.5%), Qwen B32 2418.5 → 2908.3 (+20.2%), B8
+24.2% and +25.1%. The B32 pre-fix and post-fix runs have different fingerprints because the strict kernel
source changed, not because the strict arithmetic is allowed to differ; the bit-equality tests below pin the
adapter result.

### Remaining gap to the prior vLLM controls

These vLLM numbers are the prior, separate-stage controls recorded in
`docs/strict-vllm-comparison-2026-10-25.md`, not a fresh matched control in this folder.

| Model | Our best B32 | Prior vLLM default B32 | Ratio | Remaining gap |
| --- | ---: | ---: | ---: | ---: |
| SmolLM2-360M | 3077.7 (frozen head) | 14429.4 | 21.3% | 4.69× |
| Qwen2.5-0.5B | 2907.5 (frozen head) | 13802.5 | 21.1% | 4.75× |
| TinyLlama-1.1B | 1437.3 (frozen no head) | 7791.8 | 18.4% | 5.42× |

The FP16 baseline reaches 49.9% (SmolLM2), 56.9% (Qwen) and 62.4% (TinyLlama) of those vLLM controls, so the
strict/frozen gap is not only the adapter epilogue. The near-vLLM goal is not met.

## Profile

`checks/profile-smol-b32.txt` is one warmed captured B32 SmolLM2 frozen-head trace with B = 0. Self CUDA
totals: 293.6 ms over 32 steps, 9.18 ms/step. Top kernels:

| Kernel | Self CUDA ms | Share |
| --- | ---: | ---: |
| `frozen_linear` | 95.065 | 32.4% |
| `strict_lora_finish` | 76.677 | 26.1% |
| `strict_linear` | 38.447 | 13.1% |
| `strict_attention` | 37.223 | 12.7% |
| `frozen_finish` | 14.520 | 5.0% |
| `integer_input` | 9.543 | 3.3% |
| `strict_rms_norm` | 8.704 | 3.0% |

Projection work (frozen base, fused finish and strict linear) is still 71.5% of CUDA event time. The next
kernel change should therefore target the base projection or the fused finish, not attention first. Event sums
are not wall shares; the profiler used a slightly shorter sixth prompt than the benchmark harness.

## Correctness and checks

- `checks/gpu-strict-and-decoder.log`: `180 passed` in 79 s (164 `test_strict_cuda.py` plus 16
  `test_frozen_int8_decoder_cuda.py`) with `HETEROES_GPU_ACCEPTANCE=1`.
- `checks/cpu-suite.log`: full runtime suite in the numerical environment, `3131 passed, 444 skipped` in
  226 s with `CUDA_VISIBLE_DEVICES=''`.
- `checks/mutation-lora-finish.log`: control passed; 3 of 3 mutants killed (drop scale, drop add, drop
  zero-delta select). The zero-B test case also pins `base = -0.0` with a `+0` delta, which the select mutant
  would corrupt.
- `checks/ruff.log`: format check and lint clean on the three changed Python files.
- The new tests cover ranks 1/2/3/8/16/32, odd rows/outputs, signed zero, a subnormal middle value, non-finite
  inputs/factors, CUDA-graph replay, row tiles 1/2/4/8, and bit equality against the CPU reference.

The fused kernel compiles through the same NVRTC path and PTX/SASS opcode audit as the other strict ops; a
standalone disassembly was not archived here.

## Reproduction

```bash
PY_RUNTIME=$HOME/miniforge3/envs/heteroes-match/bin/python
cd /home/pc5070ti/projects/heteroes-deepseek-flash

# One zero-B final case (repeat for every engine/model in the tables).
HETEROES_GPU_ACCEPTANCE=1 PYTHONPATH=runtime/src "$PY_RUNTIME" \
  .scratch/bench_matrix.py --engine frozen \
  --model-path .scratch/strict-integer-20261025/models/smol \
  --label smol-frozen-head --repeats 5 --frozen-head \
  --json-out docs/evidence/2026-10-25-frozen-audit-perf/raw/smol---frozen-head.json

# Nonzero-B throughput probe.
HETEROES_GPU_ACCEPTANCE=1 PYTHONPATH=runtime/src "$PY_RUNTIME" \
  .scratch/bench_matrix.py --engine frozen \
  --model-path .scratch/strict-integer-20261025/models/smol \
  --label smol-frozen-head-nonzero --repeats 5 --nonzero-adapter --frozen-head \
  --json-out docs/evidence/2026-10-25-frozen-audit-perf/raw/nonzero-adapter/smol-frozen-head.json

# Pre-fix control from the archived commit (the harness is the copy in harness/).
rm -rf /tmp/opencode/preperf && mkdir -p /tmp/opencode/preperf
git archive cc76a03d | tar -x -C /tmp/opencode/preperf
HETEROES_GPU_ACCEPTANCE=1 PYTHONPATH=/tmp/opencode/preperf/runtime/src "$PY_RUNTIME" \
  harness/bench_matrix.py --engine frozen \
  --model-path "$PWD/.scratch/strict-integer-20261025/models/smol" \
  --label smol-frozen-head-nonzero-prefix --repeats 5 --nonzero-adapter --frozen-head \
  --json-out docs/evidence/2026-10-25-frozen-audit-perf/raw/nonzero-adapter/pre-fix-smol-frozen-head.json
```

The harness copies in `harness/` are the current scratch scripts. The zero-B receipts predate the
`nonzeroAdapter` header key added for the nonzero probe; that flag defaults off and does not affect those timings.
See `SHA256SUMS`.

## Files

- `raw/*.json`: zero-B final matrix (nine receipts).
- `raw/pre-fix/*.json`: pre-fix zero-B Smol/Qwen frozen-head receipts and the intermediate row-tile Smol B32
  receipt, copied byte-for-byte from `.scratch/bench-local/20261025-recheck/`.
- `raw/nonzero-adapter/*.json`: nonzero-B final probes and the two pre-fix nonzero-B controls.
- `model-manifests.json`: consumed model files, config architecture/type/dtype, exact per-model prompts and
  prompt digests.
- `checks/`: CPU/GPU test logs, mutation log, Ruff log and the profiler table.
- `harness/`: the exact benchmark and profile scripts.

## What this does NOT show

- **No fresh matched vLLM run.** The vLLM ratios use prior separate-stage controls on an unisolated GPU. A
  matched, same-host, same-workload vLLM control is still required before an accepted ratio claim.
- **No 3060 or other-architecture result.** Every throughput number here is the local 5070 Ti. The 3060
  matrix and cross-GPU strict equality with nonzero adapters are unmeasured.
- **No trained adapters and no quality evaluation.** Both matrices use seeded, randomly initialised adapters;
  nonzero-B is a fixed normal fill, not a canonical ES perturbation. There is no trained checkpoint, finite
  quality corpus, reward, logit/KL comparison or token-quality claim.
- **No frozen-head tie claim.** The head sidecar stores an int8 approximation of the tied FP16 embedding rows;
  the FP16 embedding parameter remains storage-tied. The arithmetic is not the exact FP16 head.
- **No lifecycle measurement.** Load/prepare seconds are in the JSON, but candidate entry, perturb, restore
  and reload peaks are not measured. Memory is CUDA allocator peak, not process RSS.
- **No full model-artifact pin.** The models are local directories verified by `file_manifest`, but no frozen
  artifact bundle was written to disk and no adapter-file SHA-256 is recorded. Adapter reproducibility rests on
  the seed and the code at `f9bfd254`; the receipts do not pin the resulting tensor bytes.
- **No cross-version token identity check.** Repeat equality is within one receipt. Pre-fix and post-fix
  receipts have different engine fingerprints; only the bit-equality tests pin arithmetic equivalence.
- **No M6 completion, deployment or hardware qualification.** `hardwareQualified` remains false; the
  managed/default path is unchanged. The 32-token, sub-512-context, no-EOS workload is narrow.
- **No standalone PTX/SASS disassembly receipt** for `strict_lora_finish`, and no Nsight counter analysis.
- The TinyLlama frozen-head case is unavailable, as stated; it is not silently replaced by the B22 or FP16
  number.
