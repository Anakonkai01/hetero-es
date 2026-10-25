# HeteroES — current state

One page, kept current. Update it in place (do not stack "Latest" paragraphs). Session history lives in
[archive/handoffs/](archive/handoffs/); the previous version of this file is
[HANDOFF-history-2026-10.md](archive/handoffs/HANDOFF-history-2026-10.md).

## Tóm tắt cho chủ dự án (2026-10-25)

- Tiếp tục tự chạy toàn bộ **M0–M6**, ưu tiên kernel tổng quát tiến gần vLLM. Mã nền mới **`fb18a7b7`** thêm reference,
  CUDA integer Tensor Core và decoder riêng; [bàn giao hiện tại](handoff-codex-strict-integer-2026-10-25.md).
  M1/M2 và mục tiêu chung vẫn chưa hoàn tất; [kế hoạch đã duyệt](PLAN-SUA-HUMAN-REVIEW.md) giữ nguyên byte/phạm vi.
- Số học mới B14/B22 có RNE/scale/overflow và chứng minh bound riêng; giữ cây FP32 cũ. Scale trọng số làm mới ở đầu
  mỗi request có khóa rồi xóa khi kết thúc, đọc FP16 gốc, không giữ thêm nguyên model FP32/quantized. Chưa bật managed strict.
- Đã đo SmolLM2-360M, TinyLlama-1.1B và Qwen2.5-0.5B; parent, nhiễu chuẩn ± và restore đều được kiểm tra. B22 khớp
  token với FP32 trong bộ thử; B14 có một candidate Qwen khác token, receipt được giữ lại. Smol/Qwen khớp logits/token/
  text/reward và hash trọng số giữa 5070 Ti/3060. TinyLlama trained cross-GPU, native Windows và quality rộng còn mở.
- B22 nền trên 5070 Ti đạt B1 **177,1 / 114,5 / 171,8** và B32 **1318,2 / 830,7 / 1358,5** token/s theo thứ tự
  Smol/Tiny/Qwen: B32 tăng 1,64–2,88 lần nhưng chỉ ~9–11% vLLM default; B1 còn chậm hơn FP32 cũ.
  Prototype chuyển đổi chính xác riêng đạt B1 **249,4 / 174,4 / 254,7**, B32 **1451,6 / 918,9 / 1507,7**;
  chưa chọn vào mã nền. Không gọi đây là đã gần vLLM.
- **301 kiểm tra/target trên cả bốn GPU**, mutation **11/11**. Check-all ALL PASS: runtime **3016 pass/285 skip**,
  backend **452 pass**; gói Linux và hash source Worker/SDK đạt.
  [Kết quả nền](evidence/2026-10-25-strict-integer/RESULTS-01.md),
  [prototype chuyển đổi](evidence/2026-10-25-strict-integer/CVT-RESULTS-01.md).
- Bước tiếp: chọn tối ưu chuyển đổi sau khi đưa vét cạn vào test, rồi giảm lặp quantization/packing và cải thiện reuse
  trong tile; đo lại nhiều model/GPU. Các phần watchdog/D10, storage/replacement, managed qualification và M6 còn mở.
  [Phân việc](HUMAN-REVIEW-EFFORT-SPLIT.md). Không push/merge/deploy, đổi device state, learning run hay sửa môi trường `ai`.

## Live

Deployment remains `82c37fc`. Service status re-read after the overnight strict continuation on 2026-10-25: all three lab services stopped; no lab operation
was performed. The disk entry below is historical (2026-10-23).

| What           | State                                                                                                                                                                                                       |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Lab            | `lab.heteroes.site`, deployed clone `~/.local/share/heteroes-lab/app` at `82c37fc`; operations: [local-lab-operations.md](local-lab-operations.md)                                                          |
| Devices        | 2026-10-25 standalone probes reached local/Nhut 5070 Ti (Linux) and Thao/Quang 3060 (WSL2). Live approval/contribution was not re-read or changed; follow AGENTS.md. Native Windows acceptance remains open |
| Default engine | engine v2 noise made on the GPU (same bits as CPU; `HETEROES_NOISE_DEVICE=cpu` forces CPU)                                                                                                                  |
| Code           | Human-review branch `fix/human-review-single-model-2026-10-24`; integer feasibility core `fb18a7b7`, after captured strict/scorer/delivery/audit continuations. No push/merge/deployment                                        |
| Disk (nhan)    | `/` 90 % used; Archive (NTFS/FUSE, also personal data) **full**, holds lab recovery storage and moved run data                                                                                              |

## Open work, in order

1. **Approved human-review plan, current priority: shared strict performance and coverage.** Continue projection
   throughput beyond the captured decode implementation across model/GPU dimensions; continue the separately versioned integer Tensor Core
   arithmetic with exact-conversion, tile reuse and range/accuracy/footprint gates.
   Do not infer universal support from the current fixtures or relax exactness for a timing result. M4 qualification,
   managed weight ownership and native Windows remain open. Keep audit projection/UI for medium effort; M2 progress
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
