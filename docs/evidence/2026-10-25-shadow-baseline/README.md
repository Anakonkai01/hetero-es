# Original HF FP32 shadow versus current strict decoders

Date: 2026-10-25. Measured harness/source commit: `d9a11627`, based on DeepSeek documentation HEAD
`cb9aa2aa` after checkpoint `777a0211`. The numerical/kernel source remains `f9bfd254`; this session changes
only the benchmark harness/tests and documentation. Branch: `work/codex-frozen-perf-2026-10-25`.

The owner explicitly requested a measurement against the original evaluator retaining the complete FP32
shadow. This authorizes that baseline's simultaneous live FP16 and FP32 model copies for this experiment.
Other variants run with their existing single primary model. Each job is a separate sequential local process.

## Result

**B22 exceeds the original full-batch shadow baseline in all nine measured model/batch cases. Frozen-int8
plus LoRA exceeds it in eight of nine; TinyLlama B32 is about 1.9% slower.** All new B32 paths exceed the
original evaluator when its default chunk size of 16 is retained.

The table uses the stronger original full-batch control: B32 runs all 32 sequences in one HF call. Units are
total generated tokens/s; percentages are relative to that row's shadow control. Shadow refresh is included.

| Model | Batch | HF FP32 shadow, full batch | B22 | Frozen-int8 + LoRA |
| --- | ---: | ---: | ---: | ---: |
| SmolLM2-360M | 1 | 121.3 | 278.6 (+129.7%) | 153.2 (+26.3%) |
| SmolLM2-360M | 8 | 982.2 | 1494.8 (+52.2%) | 1100.7 (+12.1%) |
| SmolLM2-360M | 32 | 2425.7 | 3855.4 (+58.9%) | 3077.1 (+26.9%) |
| TinyLlama-1.1B | 1 | 140.1 | 187.5 (+33.8%) | 149.9 (+7.0%) |
| TinyLlama-1.1B | 8 | 690.6 | 786.2 (+13.8%) | 787.0 (+14.0%) |
| TinyLlama-1.1B | 32 | 1465.1 | 1812.4 (+23.7%) | 1437.1 (-1.9%) |
| Qwen2.5-0.5B | 1 | 144.5 | 277.5 (+92.0%) | 181.7 (+25.7%) |
| Qwen2.5-0.5B | 8 | 1110.4 | 1390.0 (+25.2%) | 1219.6 (+9.8%) |
| Qwen2.5-0.5B | 32 | 2525.8 | 3471.4 (+37.4%) | 2911.0 (+15.2%) |

Smol/Qwen frozen rows use the supported int8 sidecar for the tied head. Tiny uses its untied FP16 head;
frozen-head is unsupported for it and is not substituted. All frozen adapters are rank 8, alpha 16, seed
1234, original zero B. This retains the adapter products/strict combine path; it is not a trained adapter.

### Default chunk-16 control and close-case repeat

The original `default_chunk('float32')` is 16. Keeping that setting at B32 gives **1642.8 / 896.8 / 1591.4**
tok/s for Smol/Tiny/Qwen, respectively. This is a separate scheduling control, not the stronger full-batch
baseline in the main table. B1/B8 fit inside either chunk setting and are not redundantly measured.

Because Tiny's frozen B32 result is close to the full-batch baseline, it was repeated in A/B/B/A order,
with a new process and five timed observations at each position:

| A1: shadow | B1: frozen | B2: frozen | A2: shadow |
| ---: | ---: | ---: | ---: |
| 1465.3 | 1438.1 | 1438.0 | 1465.6 |

Pooling the ten raw observations per representation gives **1465.5 shadow versus 1438.0 frozen**, ratio
**0.98124**, or -1.88%. The close-case regression persists across this repeated process order.

### Memory and refresh

B32 Torch allocated peaks, MiB, include that batch's warmup/capture and any retained earlier graph storage
inside its process. They are not total process/driver memory or a complete lifecycle measurement.

| Model | HF FP32 shadow | B22 | Frozen-int8 + LoRA | Median shadow refresh |
| --- | ---: | ---: | ---: | ---: |
| SmolLM2-360M | 2455 | 2130 | 1892 | 3.18 ms |
| TinyLlama-1.1B | 6723 | 3002 | 2150 | 8.71 ms |
| Qwen2.5-0.5B | 3132 | 1480 | 1300 | 4.23 ms |

Every shadow receipt records distinct live FP16 and shadow FP32 parameter dtypes and bytes; shadow bytes are
exactly twice the live bytes. The unchanged `EvalModel(model, 'float32')` performs the actual deepcopy and
refresh, rather than a stand-in that loads only one FP32 model. The bound refresh callback keeps both models
alive throughout the job. Refresh executes once before each complete evaluation, including chunked B32.

## Workload and validation

- Local RTX 5070 Ti, driver 595.91.07, Linux 7.0.0-38-generic, Torch 2.13.0+cu132 / CUDA 13.2,
  Transformers 5.17.0, FP32 matmul TF32 disabled. HF uses its SDPA attention implementation.
- Same pinned safe model files and exact eight prompt-token lists for each model. The comparator checks
  files and prompt digests against the preceding frozen-audit receipts, and checks identical environment,
  source hash and common workload fields across the current representations.
- Greedy 32 output tokens, context 512, EOS stopping/prefix reuse off, repetition penalty 1.0. B1 uses
  prompt 0; B8 each prompt once; B32 repeats the eight prompts four times.
- One excluded warmup, five synchronized host-wall observations per case. Input packing, prefill, decode,
  output transfer and host overhead are included. HF shadow additionally includes its synchronized refresh.
  `refreshSeconds` and `decodeSeconds` sum to the saved raw total durations; decode-only rates are also saved.
- Full token streams and raw durations are saved, not token samples. Every timed repeat is identical inside
  its own case. B22 parent tokens match shadow in all nine measured cases. Frozen token streams differ in
  eight of nine cases; Tiny B1 is the sole equal case. This does not establish quality or all-input equality.
- Main-matrix duration min/max spread is 0.1-2.6%. The 2.6% case is Qwen shadow B1; all B32 spreads are
  below 0.5%. Sequential measurement on an unisolated desktop GPU is a remaining limitation.

`checks/harness-red-01.log` preserves the pre-implementation test failure. Targeted benchmark/precision CPU
tests: **34 passed, 1 skipped**. Scratch mutations: **4/4 killed** (skip timed refresh, wrong shadow dtype,
ignore chunking, exclude refresh from total). Ruff check/format and Git whitespace checks pass. No numerical
kernel was modified, so these checks are harness verification, not a new full-runtime or GPU acceptance claim.

## Reproduction and receipts

Use `/home/pc5070ti/miniforge3/envs/heteroes-match/bin/python` and this source worktree. Models are read-only
shared inputs at `/home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models/{smol,tiny,qwen}`.
The exact sequential jobs are in `run-matrix-01.py` and `run-tiny-abba-01.py`; their output paths already exist.
For a new reproduction, choose a fresh output path, for example:

```bash
HETEROES_GPU_ACCEPTANCE=1 PYTHONDONTWRITEBYTECODE=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
PYTHONPATH=runtime/src /home/pc5070ti/miniforge3/envs/heteroes-match/bin/python \
  runtime/scripts/benchmark_inference.py --gpu --engine hf-shadow \
  --model-path /home/pc5070ti/projects/heteroes/.scratch/strict-integer-20261025/models/qwen \
  --repeats 5 --graph-max-bytes 4294967296 --out .scratch/shadow-reproduction-02/qwen-shadow.json
```

Replace engine with `strict-integer` for B22 or `strict-frozen --frozen-head` for Qwen/Smol frozen heads;
omit `--frozen-head` for Tiny. Use `hf-shadow --hf-chunk 16 --batch-sizes 32` for the chunked control.
The benchmark rejects existing output destinations before importing/loading inference libraries.

- `provenance-01.json`: measured commit, complete runtime Python source hashes, benchmark hash, plan hash,
  initial GPU/environment and resolved permission failure. Approved plan hash remains
  `4ee6838fa47f810ee40348b5f0bc556834bf50825eb0b7b0795b5053743cb17f`.
- `raw/`: all sixteen successful process receipts and console logs, including every full generated stream,
  exact model manifests, backend/kernel identities and frozen artifact/adapter tensor hashes.
- `comparison-01.json` / `.txt`: independently recomputed main table, ratios, timing spreads, stream hashes,
  memory, token equality and input receipt hashes. `compare-01.py` is the exact comparator.
- `tiny-abba-comparison-01.json` / `.txt`: the independent close-case comparison and raw observations.
- `generated-texts-01.json`: decoded full streams for the twelve main/control receipts, with text hashes.
- `matrix-01.log`, `tiny-abba-01.log`: process sequence and terminal outcomes. All jobs completed; no GPU
  process remains from this experiment.

## What this does NOT show

- No complete ES candidate/generation speedup: canonical perturb, snapshot, restore, update, network,
  coordinator validation and export/reload are not timed. These are parent inference plus shadow-refresh
  measurements. Cold load/prepare is recorded separately, not included in warmed throughput.
- No CPU near-tie guard or `hf_compact` baseline: the original ordinary HF `generate()` path and shadow are
  used with the common fixed-length workload. Production EOS stopping and varied output lengths may change ratios.
- No trained-adapter quality or general base-quantization acceptance. Frozen-int8 changes base/head arithmetic
  and parent token streams; its throughput is a distinct model/representation tradeoff, not same-contract parity.
- No cross-GPU/3060/native Windows, matched vLLM, PTX/SASS audit renewal, complete process-RSS/lifecycle memory,
  pinned on-disk frozen bundle, package/managed acceptance, deployment or full M0-M6 completion.
- The DeepSeek numerical fixes and full handoff audit remain pending. `hardwareQualified` stays false;
  managed/default recipes and the deployed lab are unchanged. No learning, push, merge or deployment occurred.
