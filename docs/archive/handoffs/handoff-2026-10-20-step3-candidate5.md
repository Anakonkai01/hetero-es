# Handoff — plan step 2 done, step 3 (build r11 candidate5) next (2026-10-20, Claude Sonnet 5.5, xhigh)

Read `../AGENTS.md`, `plan-r11-release.md` (steps 3–8 still open) and this file. Branch `feat/v3-audit-recovery`, HEAD
`4ab54c6` (this handoff is the commit after it). `main` is still at its old commit and has not been fast-forwarded.

## Done

- Step 1 left-overs: the owner ran `git push origin --all` (`Everything up-to-date`); all 38 local tips equal their
  `origin/*` tracking refs (note appended to `evidence/2026-10-20-backup/README.md`). Not done: a fresh
  `git ls-remote origin` (blocked earlier, not retried) and the GitHub private/public check — the owner still has to
  confirm the repository is private.
- Step 2: `4ab54c6`, evidence `evidence/2026-10-20-coordinator-failure-surfacing/` (mutation checks, what changed, what
  it does NOT show) and `evidence/2026-10-20-candidate5-checks/` (`check-all.sh` ALL PASS, run alone).

## Two things that differ from the plan text (both in the evidence README)

1. The plan only asked for a severity rule, but the backend table `monitoring_events` (where device events land) was
   never read by any route, so `agent_command_failed` never reached the web. `/api/v1/events` now also lists
   `agent_command_failed` / `agent_command_deferred` from that table.
2. `reason` is sent only for the agent's own error types, with URLs masked, not `str(error)[:200]` for every exception
   (network/OS errors can carry grant URLs or private paths).

Side effect: coordinator events named `*_failed` (`generation_failed`, `scorer_failed`, `replay_failed`,
`audit_execution_failed`) are now ERROR in `/api/v1/events` (they were INFO).

## Next: step 3 (candidate5 build) — unchanged from the plan

Follow `evidence/2026-10-20-r11-candidate4/README.md`: `BUILD=lf1-<yyyymmdd>-r11-candidate5 scripts/build-apps.sh`
(output on Archive, check UUID `10443D1F443D094C` first), commit the refreshed desktop resources,
`scripts/publish-local-installers.py --prepare-only` (do not publish), source-copy check, packaged Linux Server and
Worker checks under `dbus-run-session`. Evidence `docs/evidence/<date>-r11-candidate5/` with `installers.sha256` and
`installers-prepared.json`. The agent change is in the Worker/Server runtime bundles, so a rebuild is required.

Then 4 (upgrade the isolated lab and devices; the owner must first free Quang's Windows C: to ≥ 20 GB, it had 6.9 GB),
5 (long managed run, 3 GPU workers, 50 generations), 6 (ff-merge `main`, push), 7 (flag day with the owner present),
8 (docs, close). Stop rules from the plan still apply.

## Live state (unchanged)

Public lab untouched at its deployed commit. All test devices off; the isolated lab is stopped. No SSH, GPU or lab
operation was used in this session.

Resume prompt:

> Đọc AGENTS.md, docs/handoff-2026-10-20-step3-candidate5.md và docs/plan-r11-release.md, rồi làm bước 3 của plan
> (build candidate5). Tuân thủ các luật dừng. Nói chuyện với tôi bằng tiếng Việt.
