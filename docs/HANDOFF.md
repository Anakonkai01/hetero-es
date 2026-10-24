# HeteroES — current state

One page, kept current. Update it in place (do not stack "Latest" paragraphs). Session history lives in
[archive/handoffs/](archive/handoffs/); the previous version of this file is
[HANDOFF-history-2026-10.md](archive/handoffs/HANDOFF-history-2026-10.md).

## Tóm tắt cho chủ dự án (2026-10-25)

- Tiếp tục từ repo sạch `033065d`, chủ dự án chuyển ưu tiên xhigh sang **kernel strict, hiệu năng và khả năng dùng
  chung nhiều model/GPU**; yêu cầu đọc repo vLLM và tài liệu liên quan. Lõi mới ở **`a232ad0`**;
  [bàn giao kernel](handoff-codex-strict-kernel-2026-10-25.md). Toàn bộ M0–M6 giữ nguyên, M1/M2 chưa hoàn tất.
- Đã tách graph dùng chung cho Qwen2/Llama/Mistral trong phạm vi toán tử hỗ trợ; có head tied/untied, bias và query
  width khác hidden width. Kernel theo kích thước/toán tử, không khóa checkpoint Qwen. Graph chưa hỗ trợ bị từ chối.
  [Contract](../runtime/docs/strict-decoder-v1.md), [đọc repo vLLM và bài báo](STRICT-PERFORMANCE-VLLM.md).
- Đã thêm packed prefill/decode, KV độc lập và EOS compaction; tính sẵn RoPE; row tiling và nạp coalesced qua shared
  memory có giới hạn, giữ nguyên cây cộng FP32. Không bật backend/strict policy mới cho recipe managed.
- Benchmark cùng workload trên 5070 Ti: tổng batch 32 **67,4 → 379,8 token/s (~5,6×)**; batch 1 đạt 100,5.
  vLLM default đạt 13.802,5 tổng token/s ở batch 32; batch-invariant đạt 4.697,2. Còn khoảng cách lớn.
  Đây là một checkpoint benchmark, không phải nghiệm thu mọi model; build thư viện khác nhau, GPU không cô lập.
- **215 kiểm tra trên mỗi GPU**, bốn máy; fixture ba họ/bốn layout/hai trạng thái trọng số khớp bit trên cả bốn.
  Check-all cuối **ALL PASS**: runtime CPU 2.943 pass/211 skip, backend 452 pass; mutation 23/23, gói Linux từ
  source mới đạt. Chưa nghiệm thu checkpoint Llama/Mistral thật, native Windows hay managed lifecycle.
  [Receipt và giới hạn](evidence/2026-10-25-strict-throughput/README.md).
- Lõi audit trước đó ở `1eaaecc`: trạng thái canonical, lý do drain, kết quả cũ sau đổi thế hệ và guard trước update.
  Projection/UI để phiên medium; watchdog/D10, storage/replacement và qualification còn mở.
  [Phân việc](HUMAN-REVIEW-EFFORT-SPLIT.md), [contract audit](../runtime/docs/audit-state-v1.md).
- Không push/merge, deploy, đổi approval/contribution, learning run hay sửa môi trường `ai`. GPU/SSH trong phiên này
  được chủ dự án cho phép rõ. Dự án vẫn chỉ claim hệ thống; không claim thuật toán ES mới hay model học tốt hơn.

## Live

Deployment remains `82c37fc`. Service status re-read after the strict continuation on 2026-10-25: all three lab services stopped; no lab operation
was performed. The disk entry below is historical (2026-10-23).

| What           | State                                                                                                                                                                                                       |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Lab            | `lab.heteroes.site`, deployed clone `~/.local/share/heteroes-lab/app` at `82c37fc`; operations: [local-lab-operations.md](local-lab-operations.md)                                                          |
| Devices        | 2026-10-25 standalone probes reached local/Nhut 5070 Ti (Linux) and Thao/Quang 3060 (WSL2). Live approval/contribution was not re-read or changed; follow AGENTS.md. Native Windows acceptance remains open |
| Default engine | engine v2 noise made on the GPU (same bits as CPU; `HETEROES_NOISE_DEVICE=cpu` forces CPU)                                                                                                                  |
| Code           | Human-review branch `fix/human-review-single-model-2026-10-24`; shared strict core `a232ad0`, after the scorer/delivery/audit continuation. No push/merge/deployment                                        |
| Disk (nhan)    | `/` 90 % used; Archive (NTFS/FUSE, also personal data) **full**, holds lab recovery storage and moved run data                                                                                              |

## Open work, in order

1. **Approved human-review plan, current priority: shared strict performance and coverage.** Continue projection
   throughput and bounded launch/CUDA Graph work across model/GPU dimensions; inspect integer/component Tensor Core
   arithmetic as a separate versioned research path, with an independent reference and range/accuracy/footprint gates.
   Do not infer universal support from the current fixtures or relax exactness for a timing result. M4 qualification,
   managed weight ownership and native Windows remain open. Keep audit projection/UI for medium effort; M2 progress
   watchdog/hard caps/D10 and M3 I/O/sidecar/replacement consistency remain heavy work. Strict activation still needs
   those gates. See [effort split](HUMAN-REVIEW-EFFORT-SPLIT.md) and [kernel handoff](handoff-codex-strict-kernel-2026-10-25.md).
2. **oomd / recovery-point upload loop.** Evidence and five proposed fixes:
   [evidence/2026-10-23-oomd-review/](evidence/2026-10-23-oomd-review/README.md). Policy:
   [operations-decisions-2026-10-23.md](operations-decisions-2026-10-23.md) (keep oomd on; supervisor recovers a run
   only once).
3. **Disk retention.** Policy agreed (Q1 in the decisions file), not implemented. Low-disk pause is not accepted under a
   real full disk (Q4, deferred).
4. **Benefit of extra/slower GPUs:** [next-codex-heterogeneous-benefit.md](next-codex-heterogeneous-benefit.md).
   Includes the per-generation bookkeeping that grows from ~1.7 s to ~11 s over a 600-generation run.
5. **Two audit timeouts at generation 63** of the soak (722 selected, 720 matched); reporting is fixed, cause is not.
6. Planned, not started: [plan-sdk-lab-bridge.md](plan-sdk-lab-bridge.md). Runtime polish list: [RUNTIME-TODO.md](RUNTIME-TODO.md).
7. Claims audit needs the owner's review: [CLAIMS_AUDIT.md](../runtime/docs/report/CLAIMS_AUDIT.md).

## Where things are

- Rules for agents: [../AGENTS.md](../AGENTS.md). Numerical contract: [numerical-contract.md](../runtime/docs/numerical-contract.md).
- User guides: [quickstart-vi.md](quickstart-vi.md), [worker-desktop-guide.md](worker-desktop-guide.md),
  [server-desktop-guide.md](server-desktop-guide.md). Security findings: [SECURITY-NOTES.md](SECURITY-NOTES.md).
- Design notes still in use: [resource-monitoring-design.md](resource-monitoring-design.md), ADRs in `runtime/docs/adr/`.
- Dated receipts: `evidence/YYYY-MM-DD-*/` (never rewritten). Current strict work: `2026-10-25-strict-throughput`; earlier audit work: `2026-10-25-audit-safety`.
  Historical live/soak/storage evidence remains under the 2026-10-23 folders.
- Superseded plans, handoffs and qualification notes: [archive/](archive/README.md).
