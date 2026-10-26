# Handoff for the next session after Claude's attention work — 2026-10-26

The owner closed this Claude session on 2026-10-26 (14:12 +07) because it had run long. Nothing is running:
no local or remote GPU job, no background process. The tree is clean. No push, merge, deployment, lab or
device-state change was made. The owner's latest instruction before closing was to continue the performance
work (own strict kernels approaching vLLM, then the full M0–M6 plan); resume from here.

## Where to start

- Worktree `/home/pc5070ti/projects/heteroes-codex-frozen-perf`, branch `work/codex-frozen-perf-2026-10-25`.
  Read `AGENTS.md`, `docs/HANDOFF.md`, this file, then the
  [previous Codex handoff](handoff-claude-performance-after-codex-2026-10-26.md) for the constraints (D1–D11),
  environments and the list of rejected experiments. Do not repeat those blindly.
- Commits from this session:
  - `f64453d4`: audit of the Codex checkpoint `e6053385` (clean, all manifests verified, FP16-GEMM D2
    counterexample recomputed) and a CUPTI whole-path profile without timing nodes
    ([evidence](evidence/2026-10-26-whole-path-kernel-profile/README.md)).
  - `95c331e8`: `strict_attention_gqa` and `strict_attention_split` in `runtime/src/heteroes/eval/strict_cuda.py`,
    tests in `runtime/tests/eval/test_strict_attention_split.py`, note in `runtime/docs/strict-decoder-v1.md`.
  - `70cf2eb4`: [attention evidence](evidence/2026-10-26-strict-attention-gqa/README.md) and HANDOFF update.
- **Selected runtime is now B22 `b1ef257a` plus GQA attention `95c331e8`.** Attention outputs and flags are
  bit-identical to the original kernel; the arithmetic contract did not change.

## Current numbers (batch 32, ABBA, tokens equal)

| Host | Qwen short32 | Qwen chat128 | Smol short32 | Tiny short32 |
| --- | ---: | ---: | ---: | ---: |
| 5070 Ti, before → after | 4361 → 4776 | 3953 → 4906 | 4510 → 5204 | 2322 → 2471 |
| 3060 WSL2, before → after | 1348 → 1395 | 1264 → 1387 | 1520 → 1623 | 635 → 662 |

Still about a third of the earlier vLLM control (~13835 token/s Qwen short32). The goal is not reached.

Profile after the change (`evidence/2026-10-26-strict-attention-gqa/profile/summary-02.log`), B22 Qwen chat128,
888.6 ms GPU span for 32×128 tokens:

| Category | ms | Share |
| --- | ---: | ---: |
| Projection kernels (`integer_linear`) | 576.6 | 64.9% |
| Attention | 102.6 | 11.5% |
| Projection input/finish/weights kernels | 78.0 | 8.8% |
| RMSNorm / SiLU / RoPE / add | 51.4 | 5.8% |
| GPU idle (host/launch gaps) | 63.3 | 7.1% |

The vendor-FP16 control (different arithmetic, violates D2) reaches 8.8k token/s with the new attention, so
even exact projections at vendor speed would leave a gap to vLLM; non-projection kernels then matter too.

## Next task: projections (the dominant cost)

Projections take about 4.5 ms per decode step at batch 32; just reading the 1 GB of FP16 weights once is about
1.2 ms on the 5070 Ti. Suggested order, measuring whole generations at every step:

1. Per-shape efficiency of `integer_linear` (QKV 896→1152, O 896→896, gate/up 896→2×4864, down 4864→896,
   head 896→151936): achieved bytes/s versus the memory floor and int8 MMA throughput, from CUPTI kernel
   durations (not Python launch timing). Find which shapes and which phase (FP16→limb conversion, 9 MMA
   products, split-K partials, finish) waste time. Source: `runtime/src/heteroes/eval/integer_cuda.py`,
   `integer_decoder.py`; arithmetic: `runtime/docs/` integer reference and the B22 evidence folders.
2. Then decide among: improving B22 itself (same arithmetic, so no new identity); fusing
   `integer_input`/`integer_finish` (8.8%) into the projection or neighbouring kernels; B13 radix-128
   (new arithmetic, needs its own identity, quality and cross-GPU gates; operator gain was only 1.05–1.33×,
   see `evidence/2026-10-26-strict-karatsuba/`). Prefer changes that keep B22 arithmetic.
3. Later: the ~50 ms of small kernels (fusion of RMSNorm/residual/RoPE/SiLU) and the 63 ms of host gaps.

## Gates used this session (repeat for any selected change)

- Tests first, comparing new kernels with the original kernel bit-for-bit and flag-for-flag and with the CPU
  oracle; `scripts/mutation-check.py` on scratch copies (scratch dir under `.scratch/`, not `/tmp`).
- Compile the ops source for sm_75/80/86/89/90/120 and run the PTX/SASS audit (test
  `test_ops_source_passes_the_instruction_audit_on_other_architectures`). NVRTC on sm_86 turned an unrolled
  runtime-stride loop into MUFU.RCP integer division although sm_120 was clean.
- Trained Qwen/Smol/Tiny parity (parent, seed 7001 ±σ, restored; Qwen also chat 32×128):
  `evidence/2026-10-26-strict-attention-gqa/harness/probe_attention_parity.py`, compared across hosts and with the
  sealed `b1ef257a` receipts by that folder's `summarize.py`. Whole-generation timing: `harness/bench_gqa.py`.
- 3060 WSL2 (`thao_nguyen@100.92.20.58`, commands in the previous handoff): fresh stage directories
  `/tmp/heteroes-claude-attention-20261026-0N`; script `harness/remote_3060_02.sh`.
- Native Windows on the same 3060: `harness/run_native_01.py` copies a manifest-checked archive into
  `C:\Users\Thao Nguyen\.cache\heteroes-native-strict-20261025-01\` and runs the harness in the isolated venv.
  Use fresh file names there; earlier Codex runs already used `source-attention-01.tar.gz` and similar names.
- Full `scripts/check-all.sh <fresh evidence dir>/checks` and `scripts/build-apps.sh --check <fresh .scratch dir>`
  (about 900 MB; delete it afterwards, the root disk had about 13 GiB free).

Measurement pitfalls found this session: Python `cuLaunchKernel` costs about 20 µs per launch, so event timing
of a loop of launches measures the host, not the kernel (use CUPTI via `torch.profiler`, or CUDA graphs). A
class-level `_attention_entry` toggle made both benchmark engines use the same kernel; set it per instance.

## What is still open

The performance goal; M0–M6 (watchdog/D10, storage/replacement, managed ownership/activation, installers,
qualification); B13 remains an unselected prototype; no timed native-Windows throughput. See `docs/HANDOFF.md`.
