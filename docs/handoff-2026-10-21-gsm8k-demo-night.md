# GSM8K demo night: tiers 1-2 done, two serious lab findings, tier 2b and overnight run not started

Checkpoint 2026-10-21 ~23:00 +07, branch **`feat/gsm8k-demo`** (from `feat/r11-scheduling-elastic`, not pushed). The plan
was approved by the owner (`~/.claude/plans/a-c-i-n-y-th-nh-prancy-allen.md`). Evidence:
`docs/evidence/2026-10-22-gsm8k-demo/` (README predeclared, `PREDECLARATION-tier2b.md`, **RESULTS.md**, tier1/ and tier2/
receipts). Supersedes `handoff-2026-10-21-flag-day-next.md` for "what next". Its backlog list still holds; item 9 is
VRAM/chunk.

## Done

- Owner grill (4 rounds) → plan. GSM8K v2 data (`.scratch/gsm8k/v2`: 6,973/500/1,319; `smoke` = same train, 64/64).
- `heteroes.demo` package with tests (`runtime/tests/demo`, 7 pass): DemoLab client (session from `scripts/lab-login.py`,
  retried GETs), pure frame builder, matplotlib dashboard (network + per-device timeline + reward + score histogram,
  live in VS Code, MP4/GIF export), analysis tables, self-contained replay page (`replay_template.html`, checked at 1280 px
  light and 400 px dark).
- Notebook `runtime/notebooks/gsm8k_es_lab.ipynb` (English, scientist structure), built by `build_gsm8k_es_lab.py`, kernel
  "HeteroES notebook" (`.venv-notebook`). **Not executed yet** (needs tier 2 parity, tier 3).
- Fixes: `lab_cli.Lab` sent no User-Agent, so the public lab answered 403. `managed_configuration` now passes
  `validationInterval`/`allowJoin`/`schedulerPolicy`.
- **r11 smoke run = tier 1: PASS.** Full regeneration on the 5070 Ti was ALL EQUAL and the audits matched.
- Tier 2: 160/160, 4 cross-GPU audits matched, uneven work shown; the rejoin step failed (see RESULTS).
- Tailscale switched back ON on Thao's Windows (owner OK). Credentials: lab admin login stored in memory only.

## Findings (fix candidates, none fixed)

1. **Offline member blocks release of a finished run forever** (holds every device's reservation). See RESULTS tier 2.
   This needs a timeout or an admin "release" in `agent_scheduling.release_left_members` / `_release_confirmed`. It is
   the reason nothing can run now.
2. **Public compute route cannot carry any dataset run** (`study/prepare.py` refuses public study transfers by design).
3. `/api/v1/events` is too slow to poll (HTTP 524).
4. Contribution ON does not bring a LEFT worker back (ADR-009 design); UX question for the owner. Should a reboot of a
   member (contribution resets OFF) lose it for the rest of the run?
5. A leaving worker floods `worker_left` marks every ~3 s while unreachable (100+ marks in tier 2's timeline).

## Live state at close

- Lab: tier 1 COMPLETED/released; **tier 2 coordinator COMPLETED but lab DRAINING**, holding 5070ti-nhan, 3060-thao,
  1660s and quang-3060 until quang-3060 comes back online.
- quang-3060 offline since 22:18:44 (owner will message Quang). 3060-thao is online, with Tailscale ON again. The 1660S is
  online (PCI fault, may die).
- New machine offered by the owner: **Nhựt's 5070 Ti** `heheboiz@100.108.195.50` (Tailscale `heheboiz-nhut-pc`, Linux,
  SSH key-only). The owner was given the command to add this 5070's public key. Not installed, paired or approved yet.
- No background watchers left running. The owner's `heteroes-worker run` terminal on the 5070 must stay open.

## Next, in order

1. Unblock: wait for Quang's machine (its agent confirms the stop and the lab releases tier 2). Otherwise, with the owner's
   explicit OK, release it by hand (back up the DB first). Then fix finding 1 on the branch.
2. Nhựt's 5070 Ti: SSH check, CLI install with `--coordinator`-less join (remember backlog item 4), pairing, the owner
   approves, contribution ON.
3. Tier 2 parity: `verify_managed_run.py` (copy the coordinator ledger from
   `~/.local/share/heteroes-worker/agent-state/runs/01f8c5df…`, dataset json in `~/.local/share/heteroes-worker/artifacts/study/datasets/`)
   with `--regenerate 3`.
4. Tier 2b as predeclared (`stage_events.py <log> tier2b --add`; members can include Nhựt's machine only if the
   predeclaration is amended *before* the run). Pass → tier 3 (`gsm8k.launch(lab, "tier3")`). Expect about 6-7 min per
   generation (~30+ h for 300) unless more GPUs join. Decide G with the owner.
5. Execute the notebook (nbclient), render the media (`render_video`), publish the replay page as a private Artifact,
   update RESULTS, HANDOFF and memory.
