# 2026-10-22 ~16:30: tier 3 stopped after the learning audit; next session = fix the open system bugs only

Branch **`feat/gsm8k-demo`** (not pushed). Lab still on `a198cb0` (candidate12 + `b5e1bc7`), now **idle**.

## What happened

1. The owner asked why tier 3 did not get better. A read-only audit of its ledger and weight files
   ([evidence/2026-10-22-gsm8k-demo/learning-audit/](../../evidence/2026-10-22-gsm8k-demo/learning-audit/README.md)) found
   **no system fault**: 0 of 2,304 rewards change when re-scored, 114/114 audits matched, the update has the documented
   size (applied L2 1.966 vs 1.965) and float16 keeps it, and the center drifts exactly like a random walk. The cause
   is learning, not the system: at σ = 1e-3 the ranking of candidates on 32 questions is luck (noise ratio 1.00,
   split-half 0.00), and the literature expects only ~1–3 points for a 0.5B model on GSM8K over hundreds of updates.
   The recipe (from Agentic ESOpt's 4B Sudoku profile) is noisier than the GSM8K recipe of Understanding ES.
2. **Owner decision (~16:00):** stop tier 3 and keep what is needed; the audit is the important result (about the
   system); GSM8K/learning is parked; **the next session fixes the open bugs only**, then something else runs.
3. Tier 3 cancelled 15:53 through the lab (`POST /api/v1/experiments/{id}/cancel`): CANCELLING → CANCELLED in ~1 min,
   runner `CANCELLED`, final recovery point at generation 70, every worker exited (`stopped`/`cancelled`), GPU free.
   71 updates, 2,304 results, final weights `43ec49ce…`. Parity and the final state: `evidence/2026-10-22-gsm8k-demo/
   RESULTS.md`, tier 3. Archive: `/mnt/Archive-2tb/heteroes-local/tier3-fa67c66c-20261022/`.
4. The watcher exited by itself; the 10-hourly sign-in loop was killed by PID.

## Open bugs for the next session (in order)

1. **Deploy candidate13** = `feat/gsm8k-demo`: wave 2 (per-device chunk, several GPUs, limits, watch), `b5e1bc7` (already
   live as a cherry-pick) and the **finding 10** fix `94225d2` (web live view of a long run empty). The lab is idle now,
   so nothing blocks it: lab (`deploy-lab-c12.sh` pattern) and the three Linux agents (`update-to-c12.sh` pattern), then a
   short run with `evalChunks: [16, 32, 64]` (ADR-010) and check the web live view on it.
2. **Finding 9**: a re-added member logs `worker_restarted`, not `worker_joined`; the timeline should show a re-add.
3. **Finding 11 (new, observed at the cancel, not yet confirmed as a bug)**: the 1660S was unreachable from 13:40 to the
   end (2 h 13 min), yet `state.json` kept it `alive: true, ready: true` and `lifecycle.jsonl` logged nothing until the
   drain (`worker_lost` at 15:53, `run_supervisor.py` logs it only when `stop` and `UNREACHABLE_STOP_SECONDS`). No
   restart was tried in that time. Decide whether a long-unreachable member should be marked/shown during the run.
4. **Windows app update on 3060-thao** (someone at the screen). The device belongs to another account: this account's
   `/api/v1/devices` does not list it.
5. **1660S**: offline since 13:40 (known PCI fault, hardware).
6. Old candidate9 server under xvfb (from `.scratch/isolated-lab`, started 2026-10-21 ~16:00) still running; not ours.
7. Disk: finished runs keep 4–6 GB of weights under `~/.local/share/heteroes-worker/artifacts/coordinators/` (~38 GB
   with tier 3); prunable after parity receipts **only with the owner's OK**.

Later, not next session: SDK → lab bridge ([plan-sdk-lab-bridge.md](../../plan-sdk-lab-bridge.md), grill the owner first);
any new learning run (Countdown would be the case where ES visibly helps a 0.5B model).
