# HeteroES — current state

One page, kept current. Update it in place (do not stack "Latest" paragraphs). Session history lives in
[archive/handoffs/](archive/handoffs/); the previous version of this file is
[HANDOFF-history-2026-10.md](archive/handoffs/HANDOFF-history-2026-10.md).

## Tóm tắt cho chủ dự án (2026-10-25)

- Chủ dự án kết thúc phiên hiện tại; **Codex phiên sau** audit rồi tiếp tục tối ưu hiệu năng từ nhánh DeepSeek.
  [Bản giao hiện hành cho Codex](handoff-codex-performance-after-deepseek-2026-10-25.md).
  Checkpoint `777a0211`, code `f9bfd254`: Smol/Qwen M6 B32 tăng +22,5%/+20,5% cục bộ;
  chưa có matched 3060/vLLM, artifact/adapter pin đầy đủ hay nghiệm thu strict đa GPU.
  Phiên đóng này chỉ chuẩn bị bản giao, không chạy tối ưu thêm.
- Tiếp tục toàn bộ **M0–M6**, ưu tiên kernel tổng quát tiến gần vLLM. Mã nền **`3fd704a5`** đã chọn chuyển đổi
  chính xác, chung lượng tử hóa đầu vào, split-K decode tự động và đóng gói activation một lần và cây cộng attention theo nhóm 8 giữ nguyên số học.
  M1/M2 và mục tiêu chung chưa hoàn tất; [kế hoạch đã duyệt](PLAN-SUA-HUMAN-REVIEW.md) giữ nguyên byte/phạm vi.
- Số học riêng B14/B22 giữ reference độc lập; FP32 cũ và recipe hiện hành không đổi. Đọc FP16 gốc, chỉ giữ metadata
  nhỏ trong request có khóa, không giữ thêm nguyên model FP32/quantized. Managed strict chưa bật.
- B22 trên 5070 Ti đạt B1 **277 / 188 / 278**, B8 **1494 / 784 / 1386**, B32 **3861 / 1805 / 3471** token/s
  theo thứ tự SmolLM2-360M/TinyLlama-1.1B/Qwen2.5-0.5B. A/B B32 tăng thêm **8–14%** trên 5070 Ti, **6–12%** trên 3060, đạt khoảng
  **23–27% vLLM default**. [So sánh tốc độ và mã nguồn](strict-vllm-comparison-2026-10-25.md).
- **452 test trên mỗi GPU trong bốn máy**, gồm native Windows 3060 **452 pass**; bốn fixture layout, hai precision,
  parent/changed/restored khớp Linux5070Ti. Check-all **ALL PASS**: runtime **3038 pass/371 skip**, backend452;
  tree/error-semantics mutation **6/6**; gói Linux và hash nguồn Worker/ServerSDK đạt.
  [Receipt đúng nguồn](evidence/2026-10-25-attention-tree/SELECTED-RESULTS-01.md).
- Parent, nhiễu chuẩn± và restore của ba trained model giữ nguyên so với B22 trước. Counterexample B14/FP32 cũ
  vẫn được giữ. Cả ba trained model khớp 5070 Ti/3060 đúng nguồn hiện tại, gồm cả manifest và identity. Quality rộng,
  native installer và managed lifecycle còn mở.
- Đối chiếu trực tiếp vLLM thấy QKV và gate/up được gộp thật sự; ta mới chung lượng tử hóa. Segmented grouped launch chỉ tăng khoảng 1,5–5,6% ở B32 nên chưa chọn. Profile mới: linear 66–84%, attention 10–20%
  thời gian CUDA B32; tiếp theo tập trung projection. Warp1/2, tile64/128 và chuyển đổi trọng số mới bị loại
  khi không có lợi. Không suy từ fixture sang qualification.
- Watchdog/D10, storage/replacement, managed ownership/qualification và M6 vẫn mở.
  [Phân việc](HUMAN-REVIEW-EFFORT-SPLIT.md). Không push/merge/deploy, đổi device state, learning run hay sửa `ai`.

## Live

Deployment remains `82c37fc`. Service status re-read after the overnight strict continuation on 2026-10-25: all three lab services stopped; no lab operation
was performed. The disk entry below is historical (2026-10-23).

| What           | State                                                                                                                                                                                                                                                       |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Lab            | `lab.heteroes.site`, deployed clone `~/.local/share/heteroes-lab/app` at `82c37fc`; operations: [local-lab-operations.md](local-lab-operations.md)                                                                                                          |
| Devices        | 2026-10-25 standalone probes reached local/Nhut 5070 Ti (Linux) and Thao/Quang 3060 (WSL2). Live approval/contribution was not re-read or changed; follow AGENTS.md. Native Windows source/fixtures pass; trained/installer/managed acceptance remains open |
| Default engine | engine v2 noise made on the GPU (same bits as CPU; `HETEROES_NOISE_DEVICE=cpu` forces CPU)                                                                                                                                                                  |
| Code           | Human-review branch `fix/human-review-single-model-2026-10-24`; selected integer decode core `3fd704a5`, after captured strict/scorer/delivery/audit continuations. No push/merge/deployment                                                                |
| Disk (nhan)    | `/` 90 % used; Archive (NTFS/FUSE, also personal data) **full**, holds lab recovery storage and moved run data                                                                                                                                              |

## Open work, in order

1. **Approved human-review plan, current priority: shared strict performance and coverage.** Continue projection
   throughput beyond the captured decode implementation across model/GPU dimensions; continue the separately versioned integer Tensor Core
   arithmetic with exact-conversion, tile reuse and range/accuracy/footprint gates.
   Do not infer universal support from the current fixtures or relax exactness for a timing result. M4 qualification,
   managed weight ownership and native Windows trained/installer acceptance remain open. Keep audit projection/UI for medium effort; M2 progress
   watchdog/hard caps/D10 and M3 I/O/sidecar/replacement consistency remain heavy work. Strict activation still needs
   those gates. See [effort split](HUMAN-REVIEW-EFFORT-SPLIT.md) and [kernel handoff](handoff-codex-strict-integer-2026-10-25.md).
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
