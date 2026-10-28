# Xhigh human-review continuation — handoff for lower-effort work

The owner resumed from clean `2776e88`, asking this xhigh session to prioritize difficult work and reserve
straightforward work for a later lower-effort session. This audit-core slice is now closed; do not start the product
follow-up in the same session. The approved M0–M6 plan is unchanged and incomplete; M2 is not complete.

## Checkpoint and read order

Repo `/home/pc5070ti/projects/heteroes`, branch `fix/human-review-single-model-2026-10-24`.
Code, tests, contract, effort split and evidence are committed at **`1eaaecc`**. The following handoff commit changes
documentation only; read git log for its final ID. Revalidate the actual worktree before proceeding.

1. `AGENTS.md`, `docs/HANDOFF.md`, this file.
2. [Effort split](HUMAN-REVIEW-EFFORT-SPLIT.md) and [core contract](../runtime/docs/audit-state-v1.md).
3. [Implementation status](HUMAN-REVIEW-IMPLEMENTATION.md) and [receipts/limits](evidence/2026-10-25-audit-safety/README.md).
4. Full plan: `/home/pc5070ti/projects/heteroes-review-2026-10-24/PLAN-SUA-HUMAN-REVIEW.md`.
   Earlier [Codex handoff](handoff-codex-human-review-2026-10-25.md) retains the previous completed slices.

## Completed here

- Runtime canonical audit accounting: selected/completed/matched/mismatched/pending/timed-out/skipped, disabled
  coverage, candidate deduplication and compatibility of `audit_counts()`. Missing audits never count as matches.
- Durable generation drain reasons, refusal of conflicting saved state and no new audits after closure/reopen.
  Accepted late canonical results supersede incomplete dispositions. Summaries are written to `generation_done.audits`.
- A private bounded registry shared across API rotation accepts old audit deliveries through the new HTTP endpoint.
  It retains unfinished deliveries at capacity; no unbounded accumulation of generation APIs or full text payloads.
- Run guard shared across APIs, including audit restore faults after rotation. Serialized update admission closes
  the race after the last cooperative check; already admitted records are completed normally, never rolled back.
  Restore-fault retries reattempt a failed persistence write before terminal ACK.
- Internal strict first-mismatch primitive with both text receipts, saved-stop validation and restart reconstruction.
  **Not activated for any managed recipe.** Historical hash sampling, default rate, three-mismatch ledger quarantine
  and frozen numerical paths are unchanged. No public strict policy switch was added.

## Next session: medium, then low

Use **medium** for the connected projection/UI slice. Use **low** afterward for isolated help text, examples and
receipt links. The owner asked to reserve these tasks; do not silently escalate this follow-up into a numerical or
recovery redesign.

1. Project core outcomes through `runtime/src/heteroes/product/run_supervisor.py`, `backend/experiment_view.py` and
   frontend experiment types. Read canonical ledger rows consistently and count selected candidates once. Do not
   instantiate a generation API for a read-only view. Keep existing API fields readable and distinguish old
   execution-row aggregates from candidate outcomes when needed.
2. Use durable `audit-state/gN.json` reasons for timed-out/skipped. Historical missing sidecars/logs mean unknown
   operational disposition, not success and not invented timeout. Late canonical completion overrides a disposition.
   Preserve the backend's existing unknown-selection handling when the available snapshot is incomplete.
3. Update audit UI/translations: explicit disabled, positive rate with no selected sample, incomplete/unknown,
   pending, matched, mismatched, timed-out and skipped. Completed includes mismatched; neither worker is assumed right.
   Keep old runs readable. No new SDK/API/CLI switch enabling strict behavior.
4. Add meaningful tests first and scratch mutations for projection/compatibility; browser fixtures should cover
   rate zero, no auditor, timeout, late completion and old partial evidence. Run relevant repo checks after code
   changes. Existing receipt folders are immutable; use fresh dated evidence with **What this does NOT show**.
5. Low-effort follow-ups: document frozen coverage/unsupported mid-run changes, refresh examples and index exact
   receipts. Preserve explicit zero. Packaging reruns follow runtime-content changes; Linux is not native Windows.

## Heavy work still open

- M2 D11 stage/progress watchdog and explicit finite hard caps with monotonic/restart semantics. Heartbeat remains
  connectivity, not meaningful progress; this slice did not change the old activity-based stall logic.
- M2 D10 persisted once-per-worker/run recovery, canonical reload/self-test/restore/probation and boundary rejoin;
  reconcile local poison, ledger quarantine, audit faults and supervisor state without device approval changes.
- M3 streaming/backoff, verification cache invalidation, retention dependency graph and measured long-run bookkeeping.
  New audit sidecars must be carried by replacement recovery, including reconciliation with faults newer than an
  immutable snapshot. Current recovery points retain restore faults but not the new drain/strict-stop state.
- Strict kernel speed/batching and heterogeneous GPU comparisons; M4 identity/qualification/GPU ownership/native
  lifecycle/packaging; M5 acceptance and M6 quantized frozen base plus LoRA. Broader M0 measurements remain open.

The strict primitive is not ready for promotion: token/backend/build identity and qualified recipe integration are
open, audit lease credentials are not persisted, and storage loss immediately after a failed receipt write has no
durable-stop guarantee. Directory-fsync/hard-kill/power-loss and replacement recovery acceptance remain open.
Real full-disk acceptance is still deferred. Do not mark these gates accepted from component reopen tests.

## Verification and operations

- `check-all-01.log`: **ALL PASS**. Final runtime CPU **2,900 passed, 186 skipped**; backend **452 passed**, one
  existing dependency deprecation warning. Includes source archive, format/lint/types/i18n, units, fixture browser
  and Electron checks. This full run includes the earlier audit-rate changes as well.
- Final-source scratch mutations: states **10/10**, guard/integration **17/17**. Initial invalid mutation target,
  surviving mutant and red tests are retained and explained in the evidence README. Raw pytest whitespace is
  intentionally preserved; exclude `docs/evidence/**` from source whitespace checks.
- Fresh Linux source-copy package/import checks passed; the packaged guard matches tested bytes and imports without
  Torch. Ignored workspace: `.scratch/audit-safety-linux-20261025`. No native Windows acceptance.
- Tested source fingerprints: `docs/evidence/2026-10-25-audit-safety/source-identity-01.json`. Only documentation
  changes after the core commit; no redundant full-suite rerun is needed solely for this handoff.
- Read-only deployed head `82c37fca`; all three lab services stopped. All check/mutation/package sessions returned
  terminal status; no owned fixture/probe was deliberately left running. Existing lab/workers were not changed.
- No push, merge, deployment, device approval/contribution change, learning run, GPU computation or SSH was performed.
  Historical hardware permission in older handoffs is not new authorization. Follow current AGENTS and the owner's
  current instructions; do not start lab services merely to continue coding. Keep `ai` unchanged, avoid Archive writes
  and never use `/mnt/sekai`. Commit logical groups and speak briefly in Vietnamese.
