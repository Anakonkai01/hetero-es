# Full-weight B22 paired reads, 2026-10-25

Selected runtime source: `9acf8bfa`. The owner explicitly redirected this continuation from the earlier
LoRA optimization to the full-weight core. This folder records that core change; the later owner-authorized
vendor arithmetic experiment is separate in [`../2026-10-25-fast-engine/`](../2026-10-25-fast-engine/README.md).

## Selected result

The same live FP16 model is shared by scalar-control and automatic-policy engines, with two bounded graph
workspaces. Context 512, eight canned prompts repeated to batches 1/8/32, greedy 32 output tokens, no early
EOS, one warmup and five observations per ABBA stage: ten host-wall observations per variant. Refresh is
inside the generation calls. The independent [comparer](model-comparison-01.json) rechecks streams and medians.

5070 Ti, total output tokens/s, native selected-source implementation:

| Model | Batch 8 scalar | Batch 8 selected | Gain | Batch 32 scalar | Batch 32 selected | Gain |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SmolLM2-360M | 1495.7 | 1564.5 | 4.59% | 3861.7 | 4073.2 | 5.48% |
| Qwen2.5-0.5B | 1388.9 | 1467.9 | 5.68% | 3466.7 | 3756.9 | 8.37% |
| TinyLlama-1.1B | 786.3 | 842.2 | 7.11% | 1811.3 | 1992.2 | 9.98% |

Batch 1 changes by -0.07%/+0.04%/+0.78%; its SIMT decode implementation is unchanged. The automatic policy
selects the paired read only for B22/SM120. On SM86 and for B14 it retains scalar reads. The matched 3060
automatic/control measurements therefore compare the same execution and vary by -0.47% to +0.32%; no
3060 gain is claimed.

The paired prototype on 3060 improved some shapes/models, but Tiny batch 8/32 regressed by 1.59%/3.51%.
These unfavorable results remain in `remote-prototypes-01/*-pair-load-3060-03.*`. Register/occupancy
diagnostics show that a simple register-pressure explanation is insufficient. The conservative policy
uses architecture/precision, not a model-name exception.

## Exactness and storage

The new kernel loads two aligned FP16 bit patterns as one 32-bit word, then applies the existing conversion
and radix packing independently to each half. Odd widths, unaligned base pointers and tails use guarded
scalar reads. Products, reconstruction, rounding, split-K and overflow behavior remain unchanged. There
is no persistent quantized or FP32 weight copy. Requested/effective policies and compiled builds are
identified separately. [Execution argument](../../../runtime/docs/b22-paired-weight-reads.md).

Independent CPU-reference GPU tests cover B14/B22, odd/even/tail widths, two-byte-offset storage, bias,
signed zero, FTZ inputs and finite FP16 extremes. The selected command passed 313 tests on 5070 Ti,
plus 16 frozen CUDA graph tests; the combined command passed 329 tests on 3060. Three scratch mutants
were killed: two incorrect reads and the unsafe SM86 automatic policy. Full streams and instruction
audit PTX/SASS are retained for both scalar and paired implementations on both architectures.

For each trained model, parent/canonical seed 7001 plus/minus at sigma 1e-3/restored parent were checked
on both hosts. Scalar/selected prefill-logit hashes, tokens, text and canned rewards match; trained
candidate weight hashes and inference outputs also match across hosts. Every state restores exactly.
That is 1024 candidate token positions per model/host/execution, in addition to the batch-1/8/32 parent
benchmark streams. Source and model files are pinned; `selected-source-01.json` checks matching runtime
source hashes on both hosts. The canonical noise/ES/ledger implementation was not changed.

## Preserved unsuccessful and invalid work

The initial profiles put `integer_linear` at 60.8%/72.8%/81.5% of profiled self CUDA time for
Smol/Qwen/Tiny. Row-warp reshaping, the 10 MiB conversion lookup, its 640 KiB compressed form and the
single-row MMA/split sweep were investigated. Their raw receipts remain; they were not selected.
The lookup's exhaustive conversion check establishes conversion only, not performance or model quality.

The first real-model pair-load harness assigned an unused `integer_kernels` attribute instead of the
actual `kernels`. Local/remote `*-pair-load-*-01.*` therefore measured the control twice and are invalid
for optimization claims. The corrected harness asserts the actual kernel binding/build names. Remote
attempt 02 overlapped the preceding unfinished job and was stopped; it is also excluded. Corrected
prototype controls are local attempt 02 and remote attempt 03. Native selected-source controls are
`*-selected-*-01.*`; these supply the table above. Earlier failures are not overwritten.

The first full check attempt exposed an inherited formatting issue and missing worktree-local dependency
links. Formatting was fixed with equality of all 498 active Python ASTs; existing dependencies were linked,
without installing into the shared environment. Attempt 01 was stopped after those failures; attempt 02
is incomplete after the observed host restart. Neither is a passing full acceptance receipt. The later
source continuation's full CPU/product and isolated Linux packaging receipts live in the fast-engine
folder and must be read with their recorded source scope.

## What this does NOT show

No near-vLLM result for B22, broad model quality, learning, managed ownership/lifecycle, native Windows
trained/installer acceptance or general hardware qualification. The finite model/candidate corpus does
not prove all inputs. `hardwareQualified` remains false. Later vendor inference has a different arithmetic
identity and separate evidence. No push, merge, deployment or device-state change.
