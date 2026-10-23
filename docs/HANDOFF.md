# HeteroES — current state

One page, kept current. Update it in place (do not stack "Latest" paragraphs). Session history lives in
[archive/handoffs/](archive/handoffs/); the previous version of this file is
[HANDOFF-history-2026-10.md](archive/handoffs/HANDOFF-history-2026-10.md).

## Tóm tắt cho chủ dự án (2026-10-23)

- Hệ thống chạy đúng: cùng một lần chạy cho ra trọng số giống nhau từng bit trên 1, 2, 3 máy và CPU/GPU; chạy 600 thế
  hệ liên tục được, chịu được mất mạng, tắt máy, tắt app.
- Ba việc chưa xong: (1) sự cố oomd: nghi do luồng đẩy điểm phục hồi lên lab, chưa sửa;
  (2) ổ Archive đầy, quy tắc dọn dữ liệu run chưa thành mã; (3) thêm GPU yếu gần như không giúp: đã giao Codex đào sâu.
- Dự án chỉ claim **hệ thống**, không claim ES làm mô hình giỏi hơn.

## Live

| What | State |
| --- | --- |
| Lab | `lab.heteroes.site`, deployed clone `~/.local/share/heteroes-lab/app` at `82c37fc`; operations: [local-lab-operations.md](local-lab-operations.md) |
| Devices | nhan 5070 Ti (coordinator + lab host), nhut 5070 Ti (borrowed), thao 3060 native Windows Desktop; candidate16 runtimes (CLI `a1c686050d9e`, Windows `c7d751ce8b3a`). 1660S dead; quang offline. Windows does not stay ON after a restart (owner's choice) |
| Default engine | engine v2 noise made on the GPU (same bits as CPU; `HETEROES_NOISE_DEVICE=cpu` forces CPU) |
| Code | `main` pushed; work happens on branches, then fast-forward |
| Disk (nhan) | `/` 90 % used; Archive (NTFS/FUSE, also personal data) **full**, holds lab recovery storage and moved run data |

## Open work, in order

1. **oomd / recovery-point upload loop.** Evidence and five proposed fixes:
   [evidence/2026-10-23-oomd-review/](evidence/2026-10-23-oomd-review/README.md). Policy:
   [operations-decisions-2026-10-23.md](operations-decisions-2026-10-23.md) (keep oomd on; supervisor recovers a run
   only once).
2. **Disk retention.** Policy agreed (Q1 in the decisions file), not implemented. Low-disk pause is not accepted under a
   real full disk (Q4, deferred).
3. **Benefit of extra/slower GPUs** — handed to Codex: [next-codex-heterogeneous-benefit.md](next-codex-heterogeneous-benefit.md).
   Includes the per-generation bookkeeping that grows from ~1.7 s to ~11 s over a 600-generation run.
4. **Two audit timeouts at generation 63** of the soak (722 selected, 720 matched); reporting is fixed, cause is not.
5. Planned, not started: [plan-sdk-lab-bridge.md](plan-sdk-lab-bridge.md). Runtime polish list: [RUNTIME-TODO.md](RUNTIME-TODO.md).
6. Claims audit needs the owner's review: [CLAIMS_AUDIT.md](../runtime/docs/report/CLAIMS_AUDIT.md).

## Where things are

- Rules for agents: [../AGENTS.md](../AGENTS.md). Numerical contract: [numerical-contract.md](../runtime/docs/numerical-contract.md).
- User guides: [quickstart-vi.md](quickstart-vi.md), [worker-desktop-guide.md](worker-desktop-guide.md),
  [server-desktop-guide.md](server-desktop-guide.md). Security findings: [SECURITY-NOTES.md](SECURITY-NOTES.md).
- Design notes still in use: [resource-monitoring-design.md](resource-monitoring-design.md), ADRs in `runtime/docs/adr/`.
- Dated receipts: `evidence/YYYY-MM-DD-*/` (never rewritten). Latest: `2026-10-23-overnight` (speed, faults, 600-gen
  soak), `2026-10-23-long-run-ui` (web repair, deployed `82c37fc`), `2026-10-23-oomd-review`.
- Superseded plans, handoffs and qualification notes: [archive/](archive/README.md).
