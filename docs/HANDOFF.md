# HeteroES — current state

One page, kept current. Update it in place (do not stack "Latest" paragraphs). Session history lives in
[archive/handoffs/](archive/handoffs/); the previous version of this file is
[HANDOFF-history-2026-10.md](archive/handoffs/HANDOFF-history-2026-10.md).

## Tóm tắt cho chủ dự án (2026-10-26)

- Chủ dự án ưu tiên tốc độ gần vLLM và cho phép thử số học khác. Nhánh hiện hành
  `work/codex-frozen-perf-2026-10-25`, worktree `/home/pc5070ti/projects/heteroes-codex-frozen-perf`.
  Code mới `c9a37059`; hai worktree gốc không sửa. Không push/merge/deploy, đổi device state hay learning.
- **Đường nhanh mới dùng vLLM làm backend inference**, HeteroES giữ nhiễu/candidate/restore. Batch 32 trên
  5070 Ti: Smol **14415**, Qwen **13813**, Tiny **7761** token/s, đạt **99,5–99,9%** vLLM cùng cấu hình.
  Trên 3060 đạt **99,7–100,7%**. Đây là tốc độ inference; thời gian snapshot, audit hash và xuất bản candidate
  được ghi riêng. [Bằng chứng và phạm vi](evidence/2026-10-25-fast-engine/README.md).
- View tham số HF chia sẻ trực tiếp storage QKV/gate-up của vLLM, giữ schema và hash candidate chuẩn ±
  khớp B22 trên cả hai GPU; restore đúng byte. Bộ nhỏ có Smol **163/164** chuỗi token khớp giữa GPU,
  Qwen/Tiny **164/164**; reward số chấm được **104/104** cho từng model. Không suy thành chất lượng rộng
  hoặc bit-exact đa GPU. Đường này là standalone thử nghiệm, chưa bật cho managed Worker.
- **B22 tự viết vẫn là control strict riêng**: `9acf8bfa` đọc FP16 theo cặp trên SM120, tăng batch 32
  **5,5% / 8,4% / 10,0%** cho Smol/Qwen/Tiny, đạt **4073 / 3757 / 1992** token/s. SM86 giữ scalar do
  Tiny bị chậm trong thử nghiệm. [Core B22](evidence/2026-10-25-b22-core-perf/README.md).
- LoRA strict trước đó `20856dea` tăng batch 32 khoảng **12–29%** tùy model/GPU; artifact, adapter chuẩn ±,
  token/logit và restore đã đối chiếu hai GPU. Đây là search space riêng, không phải control full-weight.
  [Bằng chứng](evidence/2026-10-25-frozen-subwarp-perf/README.md).
- FP16 graph v2 `3735d6db` sửa bản ghép trọng số bị stale khi ES ghi tại chỗ. Mọi mã noise/ES/ledger và
  recipe lịch sử giữ nguyên. Kế hoạch đã duyệt giữ hash
  `4ee6838fa47f810ee40348b5f0bc556834bf50825eb0b7b0795b5053743cb17f`; chỉ đạo mới về ưu tiên số học
  được ghi riêng trong [thiết kế đường vLLM](../runtime/docs/vllm-es-parameter-view.md).
- Nghiệm thu code `c9a37059`: full check **ALL PASS**, runtime CPU **3158 pass/459 skip**, backend **452 pass**;
  nhóm mới **17 test trên mỗi host**, mutation **4/4**. Gói Linux Worker/Server và hash nguồn SDK khớp;
  không suy thành vLLM đã chạy trong managed installer.
- Việc tiếp theo: đo candidate/update end-to-end trên workload rộng hơn, định lượng drift/chất lượng,
  đưa đường nhanh qua ownership/lifecycle và qualification trước khi chọn cho managed Worker. M0–M6,
  watchdog/D10, storage/replacement và native Windows còn mở; không tuyên bố nghiệm thu toàn bộ.

## Live

Deployment remains `82c37fc`. Service status re-read on 2026-10-26: all three lab services stopped; no lab operation was performed. The disk entry below is historical (2026-10-23).

| What           | State                                                                                                                                                                                                                                                       |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Lab            | `lab.heteroes.site`, deployed clone `~/.local/share/heteroes-lab/app` at `82c37fc`; operations: [local-lab-operations.md](local-lab-operations.md)                                                                                                          |
| Devices        | 2026-10-25 standalone probes reached local/Nhut 5070 Ti (Linux) and Thao/Quang 3060 (WSL2). Live approval/contribution was not re-read or changed; follow AGENTS.md. Native Windows source/fixtures pass; trained/installer/managed acceptance remains open |
| Default engine | engine v2 noise made on the GPU (same bits as CPU; `HETEROES_NOISE_DEVICE=cpu` forces CPU)                                                                                                                                                                  |
| Code           | Owned performance branch `work/codex-frozen-perf-2026-10-25`; strict B22 `9acf8bfa`, experimental live FP16/vLLM views `c9a37059`. No push/merge/deployment                                                                                                 |
| Disk (nhan)    | `/` 90 % used; Archive (NTFS/FUSE, also personal data) **full**, holds lab recovery storage and moved run data                                                                                                                                              |

## Open work, in order

1. **Current priority: fast inference and measured ES lifecycle.** The owner permits alternative arithmetic in a new namespace; preserve historical recipes. Continue the vLLM-backed canonical parameter-view experiment, measure candidate/update overhead and inference drift, then qualify ownership/lifecycle before managed selection. The strict control remains separately versioned. The approved plan still has open coverage work. Continue projection
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
