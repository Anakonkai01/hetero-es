# HeteroES — current state

One page, kept current. Update it in place (do not stack "Latest" paragraphs). Session history lives in
[archive/handoffs/](archive/handoffs/); the previous version of this file is
[HANDOFF-history-2026-10.md](archive/handoffs/HANDOFF-history-2026-10.md).

## Tóm tắt cho chủ dự án (2026-10-24)

- 24/10 tối: Claude làm xong kernel CUDA strict (khớp bit, token giống nhau trên 4 GPU: 2×5070 Ti, 2×3060), bắt đầu M2;
  giao lại Codex. Xem mục "Claude session result" trong [bàn giao](handoff-claude-human-review-2026-10-24.md).
- Chủ dự án đã duyệt kế hoạch human-review, rồi tạm dừng Codex và giao Claude tiếp tục.
  Đọc [bàn giao Claude](handoff-claude-human-review-2026-10-24.md) và [tiến độ](HUMAN-REVIEW-IMPLEMENTATION.md).
- Đã có prototype một model FP16; probe hữu hạn khớp trên CPU, 5070 Ti và hai 3060 WSL2. Bản tham chiếu còn quá chậm,
  chưa có kernel tối ưu, chưa thay backend chạy chính hay nghiệm thu native Windows. M2–M6 chưa triển khai.
- Bằng chứng lịch sử có replay/trọng số khớp nhiều máy và soak 600 thế hệ; không suy thành bảo đảm inference mọi input.
  Oomd/recovery I/O, retention và lợi ích GPU yếu vẫn cần sửa theo kế hoạch.
- Dự án chỉ claim **hệ thống**, không claim ES làm mô hình giỏi hơn.

## Live

Deployment/disk entries below were last recorded on 2026-10-23; live lab state was not re-read during this handoff.

| What           | State                                                                                                                                                                                                           |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Lab            | `lab.heteroes.site`, deployed clone `~/.local/share/heteroes-lab/app` at `82c37fc`; operations: [local-lab-operations.md](local-lab-operations.md)                                                              |
| Devices        | Standalone SSH/GPU probes on 2026-10-24 reached local 5070 Ti and Thao/Quang 3060 through WSL2. Live approval/contribution was not re-read or changed; follow AGENTS.md. Native Windows acceptance remains open |
| Default engine | engine v2 noise made on the GPU (same bits as CPU; `HETEROES_NOISE_DEVICE=cpu` forces CPU)                                                                                                                      |
| Code           | Human-review branch `fix/human-review-single-model-2026-10-24`, implementation head `1cf0843` (was `3914fb5`); no push/merge/deployment in this work. Later handoff commit is docs only                         |
| Disk (nhan)    | `/` 90 % used; Archive (NTFS/FUSE, also personal data) **full**, holds lab recovery storage and moved run data                                                                                                  |

## Open work, in order

1. **Approved human-review plan, handed to Claude.** Continue from the
   [handoff](handoff-claude-human-review-2026-10-24.md), preserving full scope. Next numerical gate: a checked fast
   linear kernel matching the reference; reliability/I/O fixes can proceed independently. Codex auto-run is paused.
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
- Dated receipts: `evidence/YYYY-MM-DD-*/` (never rewritten). Latest: `2026-10-23-overnight` (speed, faults, 600-gen
  soak), `2026-10-23-long-run-ui` (web repair, deployed `82c37fc`), `2026-10-23-oomd-review`.
- Superseded plans, handoffs and qualification notes: [archive/](archive/README.md).
