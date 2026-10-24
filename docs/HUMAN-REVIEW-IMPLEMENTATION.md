# Human-review implementation

Owner approved the plan and autonomous implementation on 2026-10-24, including GPU experiments and SSH to
`3060-thao`. Decisions: [ADR-012](../runtime/docs/adr/ADR-012-single-model-strict-inference.md).
Branch: `fix/human-review-single-model-2026-10-24`; base: `c9997734`.
No lab deployment or device approval changes are included.
The owner resumed Codex on 2026-10-24 from clean `ecc2d19`, preserving the full approved plan and authorizing
GPU/SSH experiments including SGLang. No push, merge, deployment, device-state change or learning run.
The [Claude handoff](handoff-claude-human-review-2026-10-24.md) remains the historical starting point.

| Milestone                                  | State                                                                                    | Next gate                                                    |
| ------------------------------------------ | ---------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| M0 contract/baseline                       | In progress: ADR, phase traces/storage inventory and real Qwen CPU lifecycle probe       | Broader pipeline timing                                      |
| M1 one-model strict backend                | Reference plus audited NVRTC kernels; Qwen 0.5B tokens agree on four GPUs (sm_120/sm_86) | Native Windows, batching/throughput, lifecycle gates         |
| M2 delivery/scorer/audit/watchdog/recovery | In progress: scorer reservation; durable delivery/local poison; bounded usage and partial monitoring | Audit controls/statuses, watchdog and D10 recovery |
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

Codex continuation: the scorer reservation now lasts through canonical commit, closing a second-scoring race;
mutation check 11/11. Delivery keeps heartbeat until terminal ACK/refusal, persists exact result/failure payloads
in a bounded private outbox, and preserves local restore poison across restart. The agent shares private delivery
storage across launches independently of the large weights cache. Mutation check 16/16; final runtime CPU suite
2,837 passed, 186 skipped. The initial full check-all caught a cancellation constructor regression, now corrected;
the other check-all steps and fresh Linux source-copy packages passed. See the retained failures and limits in
[delivery evidence](evidence/2026-10-24-human-review-resume/delivery-summary.md).
M2 and the overall M0–M6 plan remain incomplete; outbox tests do not qualify D10 automatic restore recovery.

Bounded usage delivery (2026-10-25): result/audit ACKs enqueue metrics without waiting for the sink; the coordinator
shares one queue across generations. Record/byte bounds include in-flight work, and recorded errors/drops remain
visible as partial monitoring. Queue mutations 11/11, projection mutations 3/3. Final CPU suite: 2,848 runtime tests
passed, 186 skipped; 439 backend tests passed. See [usage receipts and limits](evidence/2026-10-24-human-review-resume/usage-summary.md).

The requested [SGLang comparison](evidence/2026-10-24-sglang-probe/README.md) found cross-GPU token differences:
stock default 14/208 prompts serially and 34/208 batched; stock deterministic exceeded shared memory. A source-pinned
FP16 pipeline-stage patch ran but still differed on 2/32 prompts between 5070 Ti and Quang's 3060, with no same-host
batch/serial differences on those rows. It is not a strict replacement or a managed backend. Thao's interrupted tuned
run yielded no receipt after host sleep; the final owned-probe check is clear on both remotes.
