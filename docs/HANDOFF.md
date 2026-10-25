# HeteroES — current state

One page, kept current. Update it in place (do not stack "Latest" paragraphs). Session history lives in
[archive/handoffs/](archive/handoffs/); the previous version of this file is
[HANDOFF-history-2026-10.md](archive/handoffs/HANDOFF-history-2026-10.md).

## Tóm tắt cho chủ dự án (2026-10-25)

- Chủ dự án yêu cầu **tự chạy xuyên đêm, làm toàn bộ M0–M6**, ưu tiên lớn nhất là kernel strict tiến gần vLLM,
  dùng chung nhiều model/GPU. Checkpoint mã mới **`e05c9ab5`**, sau `81110a14`;
  [bàn giao hiện tại](handoff-codex-strict-overnight-2026-10-25.md). Mục tiêu tiếp tục còn active, M1/M2 chưa hoàn tất.
  [Kế hoạch đã duyệt](PLAN-SUA-HUMAN-REVIEW.md) nay được lưu trong repo, giữ nguyên byte và phạm vi.
- Đã thêm CUDA Graph decode với KV có bound theo owner gốc, EOS compaction, error trước trả kết quả; xóa KV giữa
  request/candidate. Thay pointer/stream/capacity thì bỏ capture; đổi trọng số tại chỗ vẫn được đọc đúng. Chọn cây con
  projection theo kích thước, giữ nguyên số học FP32. Backend/strict policy mới chưa bật cho recipe managed.
- Đã đo **Qwen2.5-0.5B, SmolLM2-360M và TinyLlama-1.1B**. Trên 5070 Ti, batch 1 đạt **209,9 / 239,9 / 133,3**
  token/s; batch 32 đạt **500,7 / 804,9 / 288,8** tổng token/s. Tương đương khoảng 40–45% vLLM default ở batch 1,
  nhưng chỉ 4–6% ở batch 32. Tính toán projection vẫn là nút thắt lớn; chưa đạt mục tiêu gần vLLM ở batch lớn.
- **255 kiểm tra trên mỗi GPU**, bốn máy; fixture ba họ/bốn layout/hai trạng thái trọng số khớp bit, 30 build/target
  có PTX/SASS audit không vi phạm. Parent Qwen/SmolLM khớp token trên 5070 Ti/3060; TinyLlama mới đo cục bộ.
  Check-all **ALL PASS**: runtime CPU **2.961 pass/233 skip**, backend **452 pass**; mutation **13/13**, gói Linux đạt.
  [Receipt và giới hạn](evidence/2026-10-25-strict-overnight/README.md). Native Windows và managed lifecycle còn mở.
- Bước ưu tiên tiếp theo là prototype Tensor Core số nguyên với **reference/identity riêng**, range/rounding/overflow,
  accuracy, perturbation sensitivity và kiểm tra nhiều model/GPU. [Đề xuất chưa triển khai](strict-integer-projection-design.md).
  Không thay cây FP32 cũ dưới định danh cũ, không coi quantization hay corpus hữu hạn là bằng chứng đủ.
- Lõi audit `1eaaecc` giữ nguyên; projection/API/UI, watchdog/D10, storage/replacement, qualification và M6 còn mở.
  [Phân việc](HUMAN-REVIEW-EFFORT-SPLIT.md). Không push/merge/deploy, đổi approval/contribution, learning run hay sửa
  môi trường `ai`. GPU/SSH đã được cho phép trong phiên này; không có thao tác trên lab đang dừng.

## Live

Deployment remains `82c37fc`. Service status re-read after the overnight strict continuation on 2026-10-25: all three lab services stopped; no lab operation
was performed. The disk entry below is historical (2026-10-23).

| What           | State                                                                                                                                                                                                       |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Lab            | `lab.heteroes.site`, deployed clone `~/.local/share/heteroes-lab/app` at `82c37fc`; operations: [local-lab-operations.md](local-lab-operations.md)                                                          |
| Devices        | 2026-10-25 standalone probes reached local/Nhut 5070 Ti (Linux) and Thao/Quang 3060 (WSL2). Live approval/contribution was not re-read or changed; follow AGENTS.md. Native Windows acceptance remains open |
| Default engine | engine v2 noise made on the GPU (same bits as CPU; `HETEROES_NOISE_DEVICE=cpu` forces CPU)                                                                                                                  |
| Code           | Human-review branch `fix/human-review-single-model-2026-10-24`; captured strict core `e05c9ab5`, after the shared/scorer/delivery/audit continuations. No push/merge/deployment                                        |
| Disk (nhan)    | `/` 90 % used; Archive (NTFS/FUSE, also personal data) **full**, holds lab recovery storage and moved run data                                                                                              |

## Open work, in order

1. **Approved human-review plan, current priority: shared strict performance and coverage.** Continue projection
   throughput beyond the captured decode implementation across model/GPU dimensions; inspect integer/component Tensor Core
   arithmetic as a separate versioned research path, with an independent reference and range/accuracy/footprint gates.
   Do not infer universal support from the current fixtures or relax exactness for a timing result. M4 qualification,
   managed weight ownership and native Windows remain open. Keep audit projection/UI for medium effort; M2 progress
   watchdog/hard caps/D10 and M3 I/O/sidecar/replacement consistency remain heavy work. Strict activation still needs
   those gates. See [effort split](HUMAN-REVIEW-EFFORT-SPLIT.md) and [kernel handoff](handoff-codex-strict-overnight-2026-10-25.md).
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
