# 2026-10-22 morning: fix wave 1 deployed and accepted, wave 2 coded (not deployed), tier 3 for the next session

Branch **`feat/gsm8k-demo`** (not pushed). Plan: `docs/plan-2026-10-22-fix-dead-machine-and-overnight.md` (owner GO
~07:00: implement, deploy, accept, without asking). Evidence: `docs/evidence/2026-10-22-fix-wave1/` (checks, builds,
deploy scripts and logs, backups) and `docs/evidence/2026-10-22-gsm8k-demo/RESULTS.md` (tiers 2c, 2d).

## Live state

- Lab: `c472d2a`, build `lf1-20261022-r11-candidate12`, since 08:13. Rollback: check out `41dc450` (candidate10) and
  put `frontend/dist-c10` back; databases copied at each stop in `/mnt/Archive-2tb/heteroes-local/backups/fix-wave1-20261022`.
- 5070ti-nhan (coordinator), 5070ti-nhut and 1660s run the candidate12 CLI as a systemd user service (linger on, so it
  starts at boot), contribution ON with **Keep ON after restart**. Runtime `f17c9d284192`.
- 3060-thao: still the candidate9 Windows app (needs someone at its screen to update). quang-3060: down (hardware).
- The 5070 Ti disk was 99 % full; the owner approved a cleanup (old m1-m3 data, pip/uv caches): 108 GB free.

## Done (wave 1, deployed)

Lab and coordinator handle a dead member (released after 10 minutes, no hand edit), an agent stops a worker whose GPU
was given back, Keep ON after restart, a device turns itself ON/OFF, CLI redone (setup in one command, service, status,
on/off, logs, doctor, update, clean, rename, forget, uninstall; updates reuse the pinned packages), Linux = CLI only and
desktop apps for Windows only, the event list in one database session, small dataset files over the public address,
re-adding a worker that is still leaving the same run.

Acceptance: stuck tier 2b released by the deployed code (06:56). Tiers 2c and 2d passed everything (dead member killed
and released, Keep ON return, OFF/LEAVE, 7 + 13 matched audits, parity) **except (b2)**: an add 0.2 s after the owner's
ON is refused 409 "Waiting for owner to turn contribution ON" (finding 7, corrected). Fixed in `b5e1bc7`, **not deployed**.

## Coded, tested, NOT deployed (wave 2)

`97c1116` per-device evaluation chunk (ADR-010, `runtime/docs/adr/ADR-010-per-device-evaluation-chunk.md`), `b32b50c`
several GPUs per machine (`heteroes-worker --gpu N`), `2f404c2` owner limits (hours, GPU temperature), `heteroes-worker
watch`, `limits --max-chunk`. Full suites passed (runtime 2605, backend 409). Not tried on real hardware yet: a machine
with two GPUs, a run with `evalChunks`.

## Next session

1. Deploy `b5e1bc7` (lab only: candidate13 build, `deploy-lab-c12.sh` pattern) and repeat (b2) (a short tier 2e, or
   run `stage_tier2c.py --no-kill --tier <new>`); by the stop rule tier 3 waits for it. Then **tier 3** (`tier3.json`, G = 300, about a day) with 5070ti-nhan, 5070ti-nhut, 3060-thao, 1660s:
   `gsm8k.launch(lab, "tier3", workers)` (retry on a connection reset: it is idempotent), then
   `.scratch/gsm8k-demo/watch.py tier3 60`. Deploying wave 2 restarts workers, so do it before or after tier 3, not during.
2. Wave 2 deploy (build candidate13, `docs/evidence/2026-10-22-fix-wave1/update-to-c12.sh` pattern for the agents,
   `deploy-lab-c12.sh` pattern for the lab), then a short run with `evalChunks: [16, 32, 64]` to accept ADR-010.
3. Windows app update on 3060-thao (and quang-3060 moves from WSL to the app when it is back).
4. Permission notes: the Claude Code classifier refuses stopping the live lab, `rm -rf`, `iptables` cuts and long
   multi-step machine updates; when the owner types `! cmd` it arrives as text, and the owner's explicit message then lets
   the AI run it.
