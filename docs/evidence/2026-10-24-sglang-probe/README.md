# SGLang cross-GPU token probe (2026-10-24–25)

Owner-requested continuation from `ecc2d19`, after reading the strict/vLLM handoff. This is a standalone comparison,
not a production backend, qualification, learning run or deployment. Pinned Qwen2.5-0.5B-Instruct revision
`7ae557604adf67be50417f59c2c2f167def9a775`, parent FP16 weights, greedy temperature zero, up to 256 new tokens.

## Result

Different prompts below mean **token IDs differ between GPUs**. A difference at one token counts that prompt once.
The same-GPU batch/serial check is a separate comparison.

| SGLang path | Cross-GPU, one sequence at a time | Cross-GPU, batched | Same GPU: batch vs serial |
| --- | --- | --- | --- |
| Stock 0.5.22, default arithmetic: nhan 5070 Ti vs Thao 3060 | **14/208 prompts differ** | **34/208 differ** | nhan 38/208 differ; Thao 21/208 differ |
| Stock 0.5.22, deterministic | No token result: launch fails on both GPUs | No token result | FP16 GEMM needs 106,496 shared bytes; hardware limit 101,376 |
| Patched FP16 GEMM, deterministic: nhan 5070 Ti vs Quang 3060 | **2/32 prompts differ** | **2/32 differ** | 0/32 differ on either GPU; the full local receipt has 0/208 |

The tuned differences are prompt indices **23 and 24** (zero-based), first different token indices **109 and 2**.
The single-sequence comparison uses identical inputs and generation limits on both GPUs, so this is a cross-GPU
counterexample even though each machine's tested batching is invariant. It does not identify one GPU as correct.

The local tuned receipt contains 208 prompts. After Thao's host slept, Quang ran the **first 32** of that exact corpus
(8 fixed plus 24 generated prompts). `summarize-final.py` checks the actual prompt IDs, model-file hashes, generation
limits, package versions, options and tuned source hash before explicitly selecting those 32 local rows. Raw receipts
are never truncated or rewritten. The local batched call contains 208 prompts; Quang's contains 32. Both match their
own single-sequence tokens on the compared rows, and the single-sequence cross-GPU comparison is independent of that
batch-composition difference.

This tested SGLang build/configuration does not satisfy HeteroES's heterogeneous token-identity requirement.
It can inform batching/throughput work; it is not promoted to the strict path. Historical strict CUDA evidence on the
208-prompt corpus remains [0 cross-GPU differences](../2026-10-24-vllm-probe/README.md); strict was not rerun here.

## Setup and reproducibility

- Source: `runtime/scripts/probe_sglang_tokens.py`; comparison guards: `runtime/tests/eval/test_probe_sglang_tokens.py`.
  Same fixed/generated prompt source as the earlier strict/vLLM experiment; default prompt IDs were checked against
  the historical vLLM receipt. Each successful SGLang receipt records model-file hashes and actual prompt token IDs.
- SGLang **0.5.22**, torch **2.14.1+cu130**, FP16, Triton attention, PyTorch sampling, disabled radix cache, CUDA graphs,
  memory fraction .35. Parent weights only. Exact Python/OS/GPU/build versions are in the raw receipts.
- Fresh isolated environments: local `.scratch/sglang-20261024-01/venv`, Thao
  `~/heteroes-sglang-20261024-xnzXz2`, Quang `~/heteroes-sglang-20261024-Es9qXF`.
  Existing worker/lab services and `ai` were not changed. No device-state or driver/global-library changes.
- NVCC/CUDA headers/runtime come from packages inside each fresh environment. `CUDA_HOME` selects its
  `site-packages/nvidia/cu13`; only this new directory receives `lib64 -> lib` and `libcudart.so -> libcudart.so.13`
  symlinks. `SGLANG_ENABLE_JIT_DEEPGEMM=0` avoids the unused DeepGEMM import's toolkit assertion.
  `SGLANG_JIT_CACHE_DIR` selects task scratch. WSL uses process-local Windows driver/JIT library paths.
- Quang initially lacked a C++ compiler. The compiler/development `.deb` packages were downloaded and extracted
  **inside task scratch**, without apt installation, sudo or system changes. `quang-compiler-{setup,test}-*.log`
  retain failures and the successful C++ smoke test. The successful probe uses its process-local CXX/compiler paths.
- Stock deterministic GEMM exceeds shared memory on both sm_120 and sm_86. The exploratory patch changes only
  FP16 persistent matmul `num_stages: 3 -> 2`, leaving source tile sizes/math unchanged. This is **patched SGLang**,
  not the stock release, and no compiler/numerical equivalence proof is claimed. `fp16-stages2.diff` and
  `fp16-stages2-source.json` pin the change; both tuned receipts have the same modified source hash.
- Initial local/Thao package installs shared hardlinks with their package caches. The trial source edits were later
  detached into independent inodes and the stock cache bytes restored to the original hash. Link counts showed no
  other environment links. `cache-isolation-01.json` records the local repair and pending remote check;
  `cache-isolation-02.json` records the completed Thao repair. Quang used task-local UV cache and copy installation.

For a fresh environment, install with `uv pip install --link-mode=copy --prerelease=allow sglang==0.5.22`.
Use both `--gpu` and `HETEROES_GPU_ACCEPTANCE=1`, the process-local toolkit/driver/compiler settings above, a local
pinned model path and a fresh `--out`. Add `--deterministic` only for that mode. The default corpus is 208 prompts;
Quang's comparison uses `--generated 24`. Never apply the patch to an existing environment or a shared cache inode.

Recompute the final summary from the repository root with a fresh output:

```bash
python3 docs/evidence/2026-10-24-sglang-probe/summarize-final.py --out /tmp/sglang-summary-fresh.json
```

`summary-final-01.json` and `summary-final-01.log` are the recorded result; input file hashes are included.
`default-comparison-01.json` is the earlier default-only comparison. Official references:
[deterministic inference](https://docs.sglang.io/docs/advanced_features/deterministic_inference),
[offline engine](https://docs.sglang.io/docs/basic_usage/offline_engine_api),
[installation](https://docs.sglang.io/docs/get-started/install).

## Performance samples (not acceptance thresholds)

Each cell is one host-wall sample on an unisolated machine, excluding measured startup. Batch throughput uses
128 sequences from copies of the eight fixed prompts; serial throughput uses the first fixed prompt.

| Mode | Batch 128, nhan / remote | One sequence, nhan / remote |
| --- | --- | --- |
| Stock default (remote = Thao) | 33,528 / 10,776 tok/s | 574 / 263 tok/s |
| Tuned deterministic (remote = Quang) | 8,382 / 4,617 tok/s | 91 / 51 tok/s |

These compare different 3060 hosts and different equality-corpus sizes. They are not paired repeats, p50/p95,
GPU kernel timing, like-for-like strict batching measurements or a reason to choose production thresholds.

## Failures, interruption and test evidence

- `sglang-nhan-default-smoke-{01,02}`: unused DeepGEMM import asserts without CUDA_HOME; `-03`: renamed server
  argument; `-04`: NVCC path absent; `-05`: pip toolkit needs lib64/libcudart aliases; `-06`: successful smoke.
  Child-process SIGQUIT may prevent a JSON receipt; the raw failure log is preserved and is not a token result.
- `sglang-thao-default-large-01.log`: missing ninja on process PATH; `-02.json`: successful default run.
- `sglang-{nhan,thao}-deterministic-large-01.log`: stock shared-memory launch failure.
- `sglang-thao-deterministic-stages2-large-01.log`: host slept, confirmed by the owner. No complete JSON receipt.
  After wake, no owned probe process or model allocation remained. No token-equality claim comes from that run.
- `sglang-quang-deterministic-stages2-prefix32-01.log`: missing cc1plus; `-02.json`: successful isolated compiler run.
- Probe CPU tests verify exact workload identity, output row count, prefix truncation, failed receipts and GPU opt-in.
  Final mutation manifest/check: `probe-mutants-02.json`, `probe-mutation-02.log`, **5/5 killed**, control **8 passed**.
  The initial manifest/check is retained; its row-count mutant also retained Python's strict-zip guard, so the final
  manifest removes both guards to test a real silent-truncation defect.

## What this does NOT show

No universal statement about every SGLang version/configuration/input, no quality or learning result, no perturbed ES
candidates/exact restore experiment, no D1 cross-process weight ownership acceptance, no native Windows run, no broad
model-family support, and no recipe/SDK/lab/runtime integration. The tuned result is **32 prompts**, not 208 or zero
differences. A passing same-GPU batching check does not establish cross-GPU equality.
