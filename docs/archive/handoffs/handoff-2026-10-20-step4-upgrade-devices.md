# Handoff — plan step 3 done, step 4 (upgrade isolated lab and devices to candidate5) next (2026-10-20, Claude Sonnet 5.5)

Read `../AGENTS.md`, `plan-r11-release.md` (steps 4–8 still open) and this file. Branch `feat/v3-audit-recovery`.
`main` is still at its old commit and has not been fast-forwarded.

## Done in this session (step 3)

| Commit | What |
|---|---|
| a162cde | Refreshed desktop resources (`runtime.tar.gz`, `profile.json`, `defaults.json`) for **candidate5**, plus `build.log` and the runtime-source comparison |
| 1c7bedc | Evidence `evidence/2026-10-20-r11-candidate5/`: prepared (not published) installers with hashes, source-copy check, packaged Linux Server and Worker checks (all PASS), README with "What this does NOT show" |

Candidate5 build: `/mnt/Archive-2tb/heteroes-local/downloads/lf1-20261020-r11-candidate5/` (Archive UUID
`10443D1F443D094C`). Hashes: `evidence/2026-10-20-r11-candidate5/installers.sha256` and `installers-prepared.json`. It
contains the step 2 change in all three places (agent, backend `/api/v1/events`, web). Nothing was published.

Not pushed yet: `4ab54c6`, `2c524dd`, `a162cde`, `1c7bedc` and this handoff. The harness blocks the model's own
`git push`; the owner runs `! cd ~/projects/heteroes && git push origin --all`.

## Next: step 4 — unchanged from the plan

Isolated lab: copy `.scratch/isolated-lab/start-c4.sh` → `start-c5.sh` and `worker5070/start-c4.sh` → `start-c5.sh`
pointing at the candidate5 Lab Server (never touch the public lab). Thao: native Windows Worker fresh install of
candidate5 + pairing to the isolated lab (data on D:); Thao WSL CLI one-line install into a c5 home. Quang: only after
the owner freed Windows C: to ≥ 20 GB (`df -h /mnt/c` from WSL first); one-line CLI install as a **GPU worker**, GPU
self-test and model qualification. Record free space on both Windows C: before and after every install.

## Owner to-do (unchanged)

1. Confirm the GitHub repository `hetero-es` is **private**.
2. Free Quang's Windows C: to ≥ 20 GB before step 4/5 (last seen 6.9 GB; Thao's C: 16.6 GB).
3. Be present for the flag day (step 7).

## Live state

Public lab untouched. All test devices off; the isolated lab is stopped. System disk: 23 GB free after deleting the
5.1 GB packaged-check output and two superseded scratch builds.

Resume prompt:

> Đọc AGENTS.md, docs/handoff-2026-10-20-step4-upgrade-devices.md và docs/plan-r11-release.md, rồi làm bước 4 của plan
> (nâng cấp lab cô lập và các máy lên candidate5). Tuân thủ các luật dừng. Nói chuyện với tôi bằng tiếng Việt.
