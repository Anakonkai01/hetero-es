# Night 2026-10-21/22: Nhựt's 5070 Ti in, tier 2 parity pass, tier 2b ran (rejoin failed, two machines died), tier 3 blocked

Checkpoint 2026-10-22 ~01:10 +07, branch **`feat/gsm8k-demo`** (not pushed). Follows
`handoff-2026-10-21-gsm8k-demo-night.md`. Evidence: `docs/evidence/2026-10-22-gsm8k-demo/` (RESULTS.md has tier 2 parity
and tier 2b; `PREDECLARATION-tier2b.md` has the amendment and the owner's decision).

## Done

- Lab unblocked by itself when quang-3060's agent came back (~23:00).
- Quang's Windows: Kernel-Power 41, no bugcheck, fatal WHEA boot record (BERT), 3 unexpected shutdowns in 30 days
  (05/10, 13/10, 21/10). Hardware or power suspicion; Quang says the monitor lost its signal. Owner: ignore for now.
- **Nhựt's RTX 5070 Ti** (`heheboiz@100.108.195.50`, Ubuntu 24.04, 16 GB, 58 GB disk free): public one-line installer,
  self-test PASS, joined `https://lab.heteroes.site` as `5070ti-nhut` (`cli-aa99b4d4ca58`), approved by the AI as admin
  (owner's instruction), agent `nohup` (log `~/heteroes-logs/agent.log`), ON. Port 8790 on this 5070 is the *old
  isolated test lab*, not the live lab: never join there.
- Tier 2 parity: **ALL EQUAL** (`tier2/parity.json`).
- Tier 2b: 160/160, 5 matched audits, rejoin step FAIL (Quang died before the OFF), see RESULTS.
- Fixes on the branch, **not deployed**: `1a11763` (lab: a left worker offline for 10 min gives its device back, also
  checked on every poll) and `e8f26a2` (coordinator: a worker unreachable for 10 min counts as stopped when the run drains;
  changes a deliberate safety rule). Backend 396 pass, runtime 2585 pass (demo tests need `.venv-notebook`).

## Live state at checkpoint

- Tier 2b: runner COMPLETED, coordinator `state.json` DRAINING (waits for quang-3060), lab assignment not released, all
  devices of tier 2b still reserved. quang-3060 offline since 23:29:19.
- 1660s came back (rebooted ~23:42), agent restarted 00:14, contribution ON.
- 5070ti-nhut, 3060-thao, 5070ti-nhan online.

## Owner decisions this night

- Tier 3 G = 300 as declared. After 2b failed: **run tier 3 anyway** (deviation recorded), with every live machine.
- Hand release of tier 2b in the lab DB for dead quang-3060 and 1660s: **approved** (script
  `.scratch/gsm8k-demo/release_tier2b.py`, dry-run by default, `--apply` backs up the DB first; requires snapshot status
  COMPLETED and live devices confirmed stopped).
- Pending: hand edit of the coordinator's `state.json` (mark quang-3060 `left: true, alive: false, confirmed: true`, backup
  first) so the coordinator reaches COMPLETED. **Not approved yet; do not do it without the owner's yes.**

## Next

1. Either the owner approves the `state.json` edit, or Quang's machine comes back (then start its agent:
   `LD_LIBRARY_PATH=/usr/lib/wsl/lib nohup setsid ~/.local/bin/heteroes-worker run`). Then `release_tier2b.py --apply` if the
   lab still holds it, then `gsm8k.launch(lab, "tier3", workers)` with the live members (`then_tier3.py` does both).
2. Tier 2b parity receipt (`tier2b/parity.json`), commit.
3. Owner review + deploy of `1a11763`/`e8f26a2` (flag-day style, with rollback).
4. Then the old list: notebook execution, media, replay Artifact.
