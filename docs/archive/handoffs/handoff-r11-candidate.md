# Handoff — r11 candidate1 (v3 worker profile, Windows v3 admission), 2026-10-19

Continues [handoff-v3-audit-recovery.md](handoff-v3-audit-recovery.md) section 5. Read `../AGENTS.md` first. Branch
**feat/v3-audit-recovery**, from `f4a3a18` to `759ca5d` plus this document. Nothing pushed, tagged, merged, published or
deployed; no lab/device state changed; `3060-thao` stays REVOKED; the live lab still runs r10 (`79876cb`).

## Done (steps 1–6 of section 5)

| Step | Result | Evidence |
| --- | --- | --- |
| 1 | Cause of the LoRA identity failure: same random draws, but native-Windows PyTorch's CPU `uniform_` rounds in float32 while Linux accumulates in double (81 of 172,032 adapter values differ by 1 FP16 ULP). A native Windows worker driven by a Linux managed coordinator consumed the transferred adapter: 8/8 cross-OS audits match, all texts/rewards/children equal to the Linux-only run. | `evidence/2026-10-19-v3-lora-cross-os` |
| 2 | `qualification_v3`: reference with a full and a LoRA cell plus the pinned adapter file; workers never make adapters (`v3.local.prepare(initial_adapter=)`); gated `runtime/scripts/build_v3_reference.py`. Reference built on the 5070 Ti; native Windows 3060 qualifies with identical evidence. | `evidence/2026-10-19-v3-qualification-reference` |
| 3 | `scripts/build-worker-profile.py` writes only a fresh directory, needs `--profile`, `--reference-dir` for desktop-v3, `--pinned-profile` for hashless report rows (identical URL only), bounded size-lookup retries. Only PEFT/Accelerate/psutil are added. | `evidence/2026-10-19-r11-profile-v3` |
| 4–5 | `qualification.main` picks v3 for a v3 reference; READY.json names the installed profile; v2/v3 evidence goes only to labs listing that version; backend admits native Windows as a **worker-only** v3 device bound to the shipped reference (`backend/constants.py DESKTOP_V3_REFERENCE`). Full check 22/22, 2,287 runtime/100 skipped, 313 backend. | `evidence/2026-10-19-r11-v3-wiring` |
| 6 | desktop-v3 resources committed (`6614e02`), unsigned candidate1 installers built into `.scratch/r11-builds/lf1-20261019-r11-candidate1/`. Packaged Linux Worker installed a fresh runtime and its own GPU self-test returned v3 evidence identical to Windows. | `evidence/2026-10-19-r11-candidate1` |

All mutation receipts are inside those folders (every listed mutant killed, survivors got tests first).

## Open items, in order

1. **Owner:** native Windows C: has ≈3.5 GB free; the r10 runtime uses 4.1 GB and an r11 runtime needs ≈3 GB to
   download plus more extracted. The owner (or the machine's owner) frees space or we add runtime-on-another-disk
   support. Do not delete user data. Then step 7 with the owner: install the Windows Worker candidate, run the v3
   self-test, restart, stop, uninstall.
2. `scripts/check-linux-server.cjs` fails at a stale "Chi tiết" UI selector (pre-existing); update it and rerun the
   packaged Lab Server check before calling the server candidate accepted.
3. Flag day is the owner's decision: deploy the r11 server, then r11 workers. The candidate's default lab URL is the live
   lab (r10), which must not pair r11 workers before the switch.
4. Decide whether the SDK should offer `initial_adapter` publicly (it exists in `v3.local.prepare`); a native Windows
   coordinator remains unsupported because its seeded adapters differ.
5. Learning experiments remain future work with their own preregistration (section 5 step 8).

## Machines and leftovers

- 3060 (SSH `thao_nguyen@100.92.20.58`, key auth; owner authorized it for this work): new small folders under
  `%LOCALAPPDATA%/HeteroES-v3-20261019/` (`diag-lora` 20 KB, `cross-os-f4a3a18` 1.7 MB, `qual-e2d6c32` 2.1 MB; the
  temporary token file was deleted) and `D:/HeteroES-v3-20261019/cross-os-lora-cache` (0.5 MB). The original worker
  installation was only read.
- Local scratch: `.scratch/v3-cross-os/`, `.scratch/v3-reference-20261019/`, `.scratch/r11-profile-*`,
  `.scratch/r11-builds/`, `.scratch/r11-packaged*/`. Archive disk: the packaged checks used the shared
  `downloads/worker-v1` cache and created one `evidence/server-proof-*` storage folder, as designed.
