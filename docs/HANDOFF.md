# HeteroES — current state

One page, kept current. Update it in place (do not stack "Latest" paragraphs). Session history lives in
[archive/handoffs/](archive/handoffs/); the previous version of this file is
[HANDOFF-history-2026-10.md](archive/handoffs/HANDOFF-history-2026-10.md).

## Tóm tắt cho chủ dự án (2026-10-26)

- **Chỉ đạo mới nhất: hoàn tất khảo sát vLLM, ghi lại, rồi tiếp tục tối ưu strict kernel riêng để gần ngang
  vLLM; đạt mục tiêu hiệu năng thì làm tiếp đầy đủ M0–M6.** Không dùng tốc độ của wrapper vLLM để đóng
  mục tiêu kernel. D2/D3 (cùng candidate/input, cùng token/reward trên GPU khác nhau) vẫn giữ.
- Nhánh `work/codex-frozen-perf-2026-10-25`, worktree `/home/pc5070ti/projects/heteroes-codex-frozen-perf`.
  Strict B22 `9acf8bfa`: batch 32 **4073 / 3757 / 1992** token/s cho Smol/Qwen/Tiny trên 5070 Ti,
  tăng **5,5% / 8,4% / 10,0%**. Mới khoảng **26–28%** vLLM đối chứng; mục tiêu chưa đạt.
  SM86 giữ scalar sau regression. [B22](evidence/2026-10-25-b22-core-perf/README.md).
- Khảo sát vLLM đã đo parent và 8 candidate chuẩn ± trên hai GPU: Qwen đổi reward **51/2421** lượt trong
  bộ raw/256 token. Kiểm tra lại chat/512 token: **7/576** lượt, cả 7 câu đã xong; điểm candidate lệch
  tối đa **1,56 điểm phần trăm**, best candidate giữ nguyên nhưng ties/hệ số ES đổi. Không suy thành
  ảnh hưởng learning nhỏ hoặc bỏ strict. [Khảo sát và giới hạn](evidence/2026-10-26-vllm-impact/README.md).
- vLLM upstream chưa hỗ trợ native Windows. Strict `3fd704a5` từng đạt 452 test trên native Win11/3060;
  bốn layout nhỏ B14/B22/changed/restore khớp Linux. Source mới/trained model lớn/installer còn mở.
- Thử nghiệm riêng `c9a37059` chia sẻ storage HF với vLLM để giữ schema, candidate hash và exact restore;
  inference gần 100% vLLM vì dùng chính engine đó. Đây là control/khảo sát standalone, chưa managed.
  `3735d6db` sửa FP16 merged GEMM bị stale khi ES ghi tại chỗ.
  [Bằng chứng riêng](evidence/2026-10-25-fast-engine/README.md).
- LoRA strict `20856dea` tăng batch 32 khoảng 12–29% tùy model/GPU; artifact/adapter/candidate/restore đã
  đối chiếu hai host. Search space riêng, không phải full-weight control.
- Source `c9a37059`: full check ALL PASS, runtime CPU 3158 pass/459 skip, backend 452; nhóm mới 17 test
  mỗi host, 4/4 mutation; gói Linux/SDK khớp. Khảo sát mới chỉ thêm harness/evidence/docs, không đổi runtime.
- Tiếp tục projection throughput, số học có đặc tả và gate chất lượng/portable/native; không sửa recipe
  lịch sử để lấy tốc độ. Kế hoạch đã duyệt vẫn giữ hash
  `4ee6838fa47f810ee40348b5f0bc556834bf50825eb0b7b0795b5053743cb17f`.
  M0–M6, watchdog/D10, storage/replacement, ownership/lifecycle và qualification vẫn còn việc.
- Không push/merge/deploy, đổi device state, learning run hay sửa môi trường `ai`. Hai worktree gốc không sửa.

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

1. **Own strict kernels approaching vLLM, then complete M0–M6.** The vLLM impact survey is recorded;
   the vendor path remains a separate control. Preserve D2/D3 across GPU architectures and the native
   Windows direction. Alternative arithmetic may have a new namespace and must pass numerical, quality,
   footprint and portability gates; historical recipes remain intact. Focus on full-weight projections,
   then remaining shared operators and lifecycle/ownership qualification. M2 watchdog/hard caps/D10,
   M3 storage/replacement, native installers and managed activation gates remain open. See the
   [approved plan](PLAN-SUA-HUMAN-REVIEW.md), [effort split](HUMAN-REVIEW-EFFORT-SPLIT.md), and
   [impact results](evidence/2026-10-26-vllm-impact/README.md).

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
