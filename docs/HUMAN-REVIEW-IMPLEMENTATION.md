# Human-review implementation

Owner approved the plan and autonomous implementation on 2026-10-24, including GPU experiments and SSH to
`3060-thao`. Decisions: [ADR-012](../runtime/docs/adr/ADR-012-single-model-strict-inference.md).
Branch: `fix/human-review-single-model-2026-10-24`; base: `c9997734`.
No lab deployment or device approval changes are included.

| Milestone                                  | State                                                                              | Next gate                                                      |
| ------------------------------------------ | ---------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| M0 contract/baseline                       | In progress: ADR, phase traces/storage inventory and real Qwen CPU lifecycle probe | Broader pipeline timing                                        |
| M1 one-model strict backend                | Not yet implemented                                                                | Complete operator reference, then heterogeneous GPU acceptance |
| M2 delivery/scorer/audit/watchdog/recovery | Not started                                                                        | Reproduce each behavior with fault/concurrency tests           |
| M3 recovery I/O and long-run overhead      | Not started                                                                        | Bounded upload/retry and consistency tests                     |
| M4 product/lifecycle/packaging             | Not started                                                                        | SDK/lab capability and native runtime acceptance               |
| M5 system acceptance                       | Not started                                                                        | End-to-end, faults, memory and throughput receipts             |
| M6 quantized base + LoRA                   | Not started                                                                        | Same strict contract without a dequantized full-model shadow   |

The current sandbox exposes no NVIDIA device nodes. SSH user configuration is readable, but `3060-thao` does not
resolve and the local Tailscale daemon is unavailable. A reachable SSH address/account was requested asynchronously;
CPU work continues. This does not establish that the physical GPUs are offline.

Initial traces distinguish refresh from rollout without changing historical executor timings or numerical identity.
They report host wall time, not synchronized CUDA kernel time. Storage inventory counts unique physical backing
storage across parameters, buffers and roles; it does not claim allocator/process/device peak memory.

Receipts and limits: [2026-10-24-human-review](evidence/2026-10-24-human-review/README.md).
The first full-model CPU probe restored exactly with matching parent hash; live weights/buffers occupied
988,065,792 bytes, CPU snapshot 988,065,536 bytes and whole-process peak RSS 2,928,791,552 bytes.
See [probe scope and limits](evidence/2026-10-24-human-review/lifecycle-summary.md).
