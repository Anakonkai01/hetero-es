# 2026-10-22 ~10:05: (b2) fixed and accepted (tier 2e), tier 3 running

Branch **`feat/gsm8k-demo`** (not pushed). Owner GO ~09:10: "Bắt đầu luôn auto run luôn" (deploy the (b2) fix, repeat
(b2), then tier 3, without asking).

## Live state

- Lab: `a198cb0` = candidate12 (`c472d2a`) + `b5e1bc7` cherry-picked, branch **`deploy/candidate13`**, backend only, since
  09:12 (`docs/evidence/2026-10-22-tier3/deploy-lab-c13.sh` + log; database copy at stop in
  `/mnt/Archive-2tb/heteroes-local/backups/c13-20261022`). Rollback: check out `c472d2a` and restart. Agents and web are
  still candidate12; `b5e1bc7` is also on `feat/gsm8k-demo` (after wave 2).
- Tier 2e (`c48ea62d...`) **passed** (`docs/evidence/2026-10-22-gsm8k-demo/RESULTS.md`): the add 0.2 s after ON is
  accepted, nhut rejoined at generation 4, 160/160, 8 audits matched, parity ALL EQUAL. Finding 9: the coordinator logs
  `worker_restarted`, not `worker_joined`, for a re-added former member, so the staging script's literal check failed.
- **Tier 3** `fa67c66c203a4afaaaad9f9215656e4d` launched ~10:01 (`tier3.json`, G = 300, about 30 h at ~6 min per
  generation), members 5070ti-nhan (coordinator), 5070ti-nhut, 3060-thao, 1660s. Receipts in `.scratch/gsm8k-demo/tier3*`:
  `watch.py tier3 60` writes `tier3-watch.jsonl`.
- The lab token (`~/.config/heteroes-demo/session.json`) lasts 12 h; a background loop signs in again every 10 h for
  48 h (`tier3-relogin.out`). If it died: `HETEROES_ADMIN_PASSWORD=... python3 scripts/lab-login.py`. A 401 means this.

## Tier 3 rules (README of the demo evidence)

A FAILED run or an audit mismatch is recorded, not restarted; a lost 1660S is recorded and the run goes on. Do not deploy
wave 2 or restart workers while it runs. At the end: final state, applied generations, audits, member leave/join,
validation every 25 generations, selected checkpoint, **one** test evaluation of it against the base, parity (ledger
replay of child hashes + regenerate every audited candidate and one generation; `verify_managed_run.py`, the 4th argument
is the run id).

## After tier 3

1. Results + parity into RESULTS.md, replay page / video.
2. Wave 2 deploy (candidate13 proper = `feat/gsm8k-demo`), then a short `evalChunks: [16, 32, 64]` run (ADR-010).
3. Finding 9 product fix (timeline shows a re-added member). Windows app update on 3060-thao (someone at the screen).
4. **SDK → lab bridge + a "you are the researcher" notebook section** (owner asked 12:30, planned for later):
   [plan-sdk-lab-bridge.md](plan-sdk-lab-bridge.md). Grill the owner on the API first.

## Midterm demo (12:15, `7c48403`)

- Notebook `runtime/notebooks/gsm8k_es_lab.ipynb` (committed without outputs) runs offline from saved records; tier 3
  snapshot at generation 25 in `docs/evidence/2026-10-22-gsm8k-demo/tier3-g25/` (validation 0.608 → 0.606).
- Executed copy + HTML + videos + replay pages: `.scratch/gsm8k-demo/midterm/` and
  `/mnt/Archive-2tb/heteroes-local/midterm-demo-20261022/` (not in git, ~11 MB).
- Refresh later: `PYTHONPATH=runtime/src .venv-notebook/bin/python docs/evidence/2026-10-22-gsm8k-demo/snapshot.py tier3
  <dir>` then `media.py <dir> --video`.
- 1660S: dropped 10:19, back 11:01, dropped again 11:16 (unreachable). Finding 10: lab timeline of a long run is partial.

## Finding 10 fix (14:10, `94225d2`, NOT deployed)

`bounded_snapshot` (coordinator side, `runtime/src/heteroes/product/agent.py`) now keeps a long run's newest generations
whole, so the web's live view and replay work again. Tests: runtime 2608 passed; mutation 5/5. Deploy needs a new runtime
build on the coordinator machine (5070ti-nhan), which restarts the coordinator: either after tier 3 ends (~2026-10-23
11:00) or, if the owner approves, as a deliberate coordinator stop + recovery during tier 3 (never staged on real
machines yet). Owner decides after the midterm demo. Meanwhile: video/replay of tier 3 from the ledger
(`heteroes.demo.ledger_view`), `.scratch/gsm8k-demo/midterm/tier3-now.*`.
