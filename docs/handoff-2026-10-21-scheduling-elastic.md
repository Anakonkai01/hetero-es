# Tail-aware scheduling, elastic membership, candidate7 built — next: candidate7 checks, devices, acceptance

Checkpoint 2026-10-21 ~11:00 +07, branch `feat/r11-scheduling-elastic` (from `feat/v3-audit-recovery` `df2ba0d`).
Everything is committed locally and **nothing is pushed**. Main remains `086c282`, the public r10 lab is unchanged, and
nothing was published. No subagents (owner rule).

## Why this work exists

The owner asked why the measured-best dispatch policy B4 `GreedyTail` was not used in the product. An audit found
that the product had hard-coded Greedy since `51e1b2a`; that was an omission, not a decision. The audit also found
11 related gaps (F1–F12 in `~/.claude/plans/proud-roaming-charm.md`).

The owner approved fixing them **before** the 50-generation acceptance, with these choices:

- the acceptance runs on candidate7;
- elastic membership, both manual and opt-in `allowJoin`;
- limits derived from measured speeds and aware of heartbeats;
- the dead policy names removed, with `greedy-tail` as the default;
- the acceptance includes a mid-run join and leave;
- `privateLabUrl` only after sign-in.

Design: `runtime/docs/adr/ADR-009-scheduling-and-elastic-membership.md`.

## Done (commits, oldest first)

| Commit           | What                                                                                                                                                                         |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| d92ffcb, df2ba0d | GTX 1660 SUPER candidate6 qualification: self-test PASS, nine-case probe 9/9 exact vs 5070 (`evidence/2026-10-21-1660s-candidate6-qualification/`)                           |
| 44e27fc          | ADR-009 and predeclaration `evidence/2026-10-21-scheduling-elastic/`                                                                                                         |
| dd875c6          | Dispatch: AdmittedOnly forwards hooks and `set_admitted`; heartbeat liveness for GreedyTail; `SpeedBook.from_ledger`                                                         |
| a34c45f          | `greedy-tail`/`greedy` in runner, supervisor, backend, web, `heteroes serve --scheduler`; dead names removed; heartbeat-aware stall; derived limits; audits chosen/completed |
| d148231          | Elastic membership end to end (details below)                                                                                                                                |
| 37723d6          | `privateLabUrl` moved to the signed-in capabilities; desktop keeps the stack of an unclassified action failure                                                               |
| cce2f64          | CPU gate **23/23 ALL PASS** (runtime 2574/102 skipped, backend 392), mutation receipts; `RESULTS.md`                                                                         |
| b2eaecd, 638f8e1 | Candidate7 predeclaration; build `lf1-20261021-r11-candidate7` exited 0; refreshed desktop resources committed; `installers.sha256`                                          |

What `d148231` adds:

- **Ledger:** additive `membership` and `expiry` tables. The schema stays 6, unlike the plan's schema 7 (see ADR-009 §6).
- **Runner:** `product/membership.py`.
- **Agent:** `UPDATE_MEMBERSHIP`.
- **Supervisor:** starts joined workers and stops left ones; a left worker is marked `left` and is not polled again.
- **Lab:** `POST /api/v1/experiments/{id}/workers`, `allowJoin` auto-join, GPU release when a left worker is confirmed stopped.
- **Contribution OFF:** a worker that is not the coordinator and not the last member now LEAVES instead of cancelling.
- **Web:** members panel and timeline events.

Candidate7 runtime SHA256:

- Worker `57b0faf6d31a394afef5fd4760f1d0da6ebbe4e922dce5fb9eea392917c3adc7` (CLI runtime directory `57b0faf6d31a`).
- Server `fbb2cb7c8dbe6181b3f7089ac23fcd86f19ee813bad626d00bafcf376ee3926a`.

Output: `/mnt/Archive-2tb/heteroes-local/downloads/lf1-20261021-r11-candidate7`. Check UUID 10443D1F443D094C before any
write. Desktop profile directories hash the profile; read them, do not guess them from the bundle hash.

## Next, in order

1. **Candidate7 package checks**, as candidate6 did (`evidence/2026-10-20-r11-candidate6/`):
   - `publish-local-installers.py --packages <out> --build lf1-20261021-r11-candidate7 --prepare-only` into
     `evidence/2026-10-21-r11-candidate7/`.
   - Compare every runtime source byte in the Worker and Server archives with the source. `product/membership.py`
     must be present.
   - Run the source-copy packaging check, then `check-linux-server.cjs` and `check-linux-packaged.cjs --phase install`
     under `dbus-run-session`.
   - **The system disk has only about 10 GB free.** Put the `--output` and XDG directories on the Archive volume.
     Old candidate1–3 scratch builds (`.scratch/r11-builds` 6.1 GB, `.scratch/r11-packaged` 4.9 GB) could be removed,
     but only with the owner's OK.
2. **Isolated lab and devices on candidate7.**
   - Create `.scratch/isolated-lab/start-c7.sh`; the 5070 was rebooted, so the lab (8790) and the 5070 desktop are
     currently stopped.
   - Restart the tailnet-only installer HTTP on 8802 from the candidate7 directory; it was stopped at the close.
   - Upgrade every device: 5070 desktop, Thao Windows (data on D:), Thao WSL CPU (`~/.local/share/heteroes-c4-cpu`),
     Quang WSL GPU (`~/.local/share/heteroes-worker`; recheck C: ≥ 20 GB), and the 1660S CLI.
   - **1660S SSH:** use `-o HostKeyAlias=heteroes-worker-1660s`; the host key is stored under the hostname, not the IP.
     Its CLI is candidate6 in `~/.local/share/heteroes-worker`.
   - Join any new machines that arrive tonight.
   - Self-test every device. Run the nine-case probe only on GPUs not yet qualified: numerics are unchanged, and
     5070, both 3060s and the 1660S are already exact. Use `evidence/2026-10-21-1660s-candidate6-qualification/compare.py`,
     and copy the `.jsonl` dataset files too.
3. **Redeclare the acceptance** for candidate7. The new folder replaces the candidate6 predeclaration
   `evidence/2026-10-21-long-multimachine-run-candidate6/`.
   - **Configuration:** greedy-tail; Thao WSL CPU coordinator; pop 8, batch 8, max 32, 50 generations, audit 0.05;
     decoder `hf_fp32_cpu_guard_v1`; a new seed namespace.
   - **Events:** the 1660S (or a new machine) joins around g10 through the members panel or the endpoint, and leaves
     around g30. Quang is hard-stopped around g20 and restarted about 300 s later.
   - **Monitor:** adapt the monitor and fault helpers; they must request pause on a mismatch.
   - **Verifiers:** add `membership_violations == []` and explicit `expiry` rows to the copied verifiers.
   - **Stop rule:** any genuine mismatch → handoff/stop.
4. Then follow `plan-r11-release.md` steps 6–8: Windows uninstall, FF main and push, flag day with an "đồng ý" for
   each irreversible step, then docs and memory.

## Retained, unexplained

- **`test_v3_product[hf_fp32_cpu_guard_v1-space0]`** failed once, during edits made while the suite was running. Later
  clean runs pass.
- **The desktop Worker unit suite** failed once in 7 runs, with the test name not captured. 6 later runs pass.
- **The first Windows candidate6 self-test `ACTION_FAILED`.** Candidate7 now logs the stack if it happens again.
- **The original attempt2 run** `e07deeb168ae4baaba3ac770b89043a6` stays PAUSED and preserved.
