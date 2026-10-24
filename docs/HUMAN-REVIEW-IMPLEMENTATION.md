# Human-review implementation

Owner approved the plan and autonomous implementation on 2026-10-24, including GPU experiments and SSH to
`3060-thao`. Decisions: [ADR-012](../runtime/docs/adr/ADR-012-single-model-strict-inference.md).
Branch: `fix/human-review-single-model-2026-10-24`; base: `c9997734`.
No lab deployment or device approval changes are included.
Owner paused Codex auto-run and requested continuation by Claude on 2026-10-24;
read the [handoff](handoff-claude-human-review-2026-10-24.md). Implementation head at handoff: `3914fb5`.

| Milestone                                  | State                                                                                    | Next gate                                                    |
| ------------------------------------------ | ---------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| M0 contract/baseline                       | In progress: ADR, phase traces/storage inventory and real Qwen CPU lifecycle probe       | Broader pipeline timing                                      |
| M1 one-model strict backend                | Reference plus audited NVRTC kernels; Qwen 0.5B tokens agree on four GPUs (sm_120/sm_86) | Native Windows, batching/throughput, lifecycle gates         |
| M2 delivery/scorer/audit/watchdog/recovery | Not started                                                                              | Reproduce each behavior with fault/concurrency tests         |
| M3 recovery I/O and long-run overhead      | Not started                                                                              | Bounded upload/retry and consistency tests                   |
| M4 product/lifecycle/packaging             | Not started                                                                              | SDK/lab capability and native runtime acceptance             |
| M5 system acceptance                       | Not started                                                                              | End-to-end, faults, memory and throughput receipts           |
| M6 quantized base + LoRA                   | Not started                                                                              | Same strict contract without a dequantized full-model shadow |

Execution permissions were updated after the initial sandbox failures. The local RTX 5070 Ti is accessible and key
SSH works to `thao_nguyen@100.92.20.58` and `quang@100.99.227.8`. Both remote hosts expose RTX 3060 GPUs through WSL2.
The old socket/device-denial receipts remain as observations of the earlier environment. No sudo was needed.
For standalone probes, a process-local library path selects the Windows-provided driver/JIT libraries; Quang's
system JIT library otherwise segfaults during CUDA discovery. No global driver or lab configuration was changed.

Initial traces distinguish refresh from rollout without changing historical executor timings or numerical identity.
They report host wall time, not synchronized CUDA kernel time. Storage inventory counts unique physical backing
storage across parameters, buffers and roles; it does not claim allocator/process/device peak memory.

Receipts and limits: [2026-10-24-human-review](evidence/2026-10-24-human-review/README.md).
The first full-model CPU probe restored exactly with matching parent hash; live weights/buffers occupied
988,065,792 bytes, CPU snapshot 988,065,536 bytes and whole-process peak RSS 2,928,791,552 bytes.
See [probe scope and limits](evidence/2026-10-24-human-review/lifecycle-summary.md).

The experimental [numerical reference](../runtime/docs/strict-reference-v1.md) executes the graph directly from
the live FP16 weights with bounded widening and specified FP32 operations. The real 0.5B CPU and local GPU one-token
probes restore exactly on CPU and all three GPUs. Portable operator/tiny-Qwen probes also agree bit-for-bit on them. These finite
checks do not qualify the backend for managed use. The eager full-model forward is far too slow for promotion;
kernel optimization, native Windows, recipe/capability integration and cross-process weight ownership remain open.
See [reference receipts and scope](evidence/2026-10-24-human-review/reference-summary.md), including the full CPU checks
and the targeted retry of a stale live-view browser selector.

Strict CUDA kernels (2026-10-24, Claude): `eval/strict_cuda.py` and `eval/qwen2_strict_cuda.py` reproduce the
reference bit for bit, per kernel and per graph, and are audited at the PTX/SASS level. On the pinned Qwen2.5-0.5B, a
parent and 8 antithetic candidates × 8 prompts (4,387 tokens) agree across the local 5070 Ti, Nhựt's 5070 Ti and
both 3060s (WSL2). Speed: about 60 tokens/s per sequence on a 5070 Ti and 23–26 on a 3060; the eager reference
took 46–149 s per token. Peak allocation is about 1.08 GB, close to one FP16 weight set. See
[strict CUDA receipts](evidence/2026-10-24-strict-cuda/README.md). Not yet: native Windows, batched sequences,
managed lifecycle/recipe integration and packaging.
