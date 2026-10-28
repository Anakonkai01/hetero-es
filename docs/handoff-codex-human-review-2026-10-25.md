# Codex human-review continuation — session closed by owner (2026-10-25)

The owner explicitly asked to close the session to conserve usage. Stop automatic work here; resume when asked.
The approved full plan is **not complete** and has not been narrowed. No goal was marked complete.

## Repository and read order

Repo `/home/pc5070ti/projects/heteroes`, branch `fix/human-review-single-model-2026-10-24`.
This handoff is committed with the audit-coverage slice on top of `5c5ae49`; use git log for its final commit ID.
The working tree is intended to be clean. Revalidate actual state before doing more work.

1. `AGENTS.md`, `docs/HANDOFF.md`, this file and `docs/HUMAN-REVIEW-IMPLEMENTATION.md`.
2. Approved full plan: `/home/pc5070ti/projects/heteroes-review-2026-10-24/PLAN-SUA-HUMAN-REVIEW.md`.
3. `docs/handoff-claude-human-review-2026-10-24.md` for the strict numerical implementation and hardware paths.
4. Evidence linked below. Existing evidence/artifacts are immutable; make a new receipt for new checks.

## Completed in this Codex continuation

- `8dcfb6a`: mutation-checked scorer and fixed the gap between scoring completion and canonical commit. Keep the
  singleflight reservation through commit; publish unexpected errors to existing waiters. Final mutation check 11/11.
- `c80969d`: heartbeat through delivery/pending retries; bounded private durable result/failure outbox; local restore
  poison survives lost report ACK and restart. Agent relaunches share a private delivery directory independently of
  large weights cache. Final mutation check 16/16. D10 automatic recovery is not implemented.
- `82368bf`: SGLang experiment. Stock default differs between 5070 Ti/Thao 3060 on 14/208 serial prompts and 34/208
  batched prompts. Stock deterministic exceeds shared memory; an isolated FP16 num_stages 3->2 patch runs but still
  differs between 5070 Ti/Quang 3060 on 2/32 prompts. Same-host tested batch/serial outputs agree in tuned mode.
  Parent weights only; not a strict replacement or production integration.
- `5c5ae49`: bounded best-effort usage queue, shared across generation APIs; includes active work in capacity,
  preserves idempotent keys, refuses changed pending metadata and does not hold canonical result ACKs behind I/O.
  Errors/drops remain partial in managed projections. Queue mutations 11/11; projection mutations 3/3.
- This final slice: audit rate 0..1/default .05 from SDK/CLI through API, managed runner and UI; pin operational
  settings in `audit-config.json`; preserve explicit zero in templates/commands; backend hash selection uses the
  configured rate. Numerical recipe/plan/record/child identities stay equal between coverage 0 and 1 in CPU tests.
  Runtime/backend/frontend mutations 8/8, 4/4, 2/2; targeted runtime 58/backend 66 passed; browser contract passed.

## Evidence and verification limits

- `docs/evidence/2026-10-24-human-review-resume/README.md`, `delivery-summary.md`, `usage-summary.md`.
  Initial full check-all caught a cancellation constructor regression; it was corrected and raw failure retained.
  Last complete CPU suites, at `5c5ae49`: runtime 2,848 passed, 186 skipped; backend 439 passed, one warning.
  Full fixture browser/Electron/type/i18n checks and fresh Linux source-copy packages also ran in that continuation.
- `docs/evidence/2026-10-24-sglang-probe/README.md`: raw successful/failed/interrupted receipts and pinned patch.
  Thao slept mid tuned run; owner confirmed this and resumed the host. No complete token receipt from that run.
  Initial local/Thao source edits touched package-cache hardlinks; caches were restored to stock hashes and variant
  inodes detached. No other environment links existed. Quang used copy installation and a task-local UV cache.
  No owned probes remained on either remote in the final observation receipt. Existing ai/worker/lab environments
  and system compiler/driver configuration were not changed; Quang compiler packages were extracted into scratch.
- `docs/evidence/2026-10-25-audit-controls/README.md`: final slice's targeted tests/mutations/browser. **No full
  check-all/runtime/backend suite rerun after this audit-rate slice.** Do not relabel the prior full result as a
  complete matrix for the final head. The temporary browser fixture process has terminated.

## Next actions, preserving the approved order

1. Finish M2 audit states: selected/completed/matched/mismatched/timed-out/skipped, clear disabled/incomplete UI.
   Keep `audit_counts()` compatibility where needed. Derive completed/matched status from canonical ledger reads;
   avoid changing frozen ledger/noise/ES behavior. Preserve historical default sampling and three-mismatch policy.
2. For the new strict path only, first text mismatch must stop before the next admitted update and retain both
   execution receipts without assuming which worker is correct. Design a shared/persisted run-level stop gate so a
   late result from an older generation cannot be forgotten when the API rotates. Do not attach this policy to a
   nominally strict recipe before its backend/identity gates exist (M4).
3. Stage/progress watchdog plus finite explicitly configured hard caps; heartbeat is connectivity only. Then D10:
   persisted once-per-worker/run allowance, stop/report, canonical reload, self-test/restore verification, probation
   and generation-boundary rejoin. Reconcile local outbox poison, ledger quarantine, audit faults and supervisor
   state; do not reset coordinator recovery limits or modify device approval/contribution.
4. M3: bounded recovery streaming/backoff, verification cache with safe invalidation, retention dependencies and
   early/middle/late bookkeeping measurements. Keep essential replay/result data; real full-disk acceptance deferred.
5. Strict speed: precompute RoPE, reduce kernel launch cost, multi-row and multi-sequence batching with exact
   arithmetic and token comparison on supported GPUs. Borrow vLLM/SGLang techniques; neither tested vendor path
   replaces the strict implementation. Native HF baseline and owner-selected performance thresholds remain open.
6. M4 recipe/backend identity, qualification cache namespace, one weight set per physical GPU across managed roles,
   SDK/lab/lifecycle and native packaging; M5 system acceptance; M6 frozen quantized base plus ES LoRA.

## Authorization and operations

The owner authorized autonomous implementation/commits, GPU (`HETEROES_GPU_ACCEPTANCE=1`) and explicitly renewed
full SSH access in this conversation. Named hosts: Thao `thao_nguyen@100.92.20.58`, Quang `quang@100.99.227.8`,
Nhut `heheboiz@100.108.195.50`. Read current AGENTS.md and the owner's instructions; this handoff itself is not a
new authorization. Use new scratch only, keep existing workers/lab alone, and never alter ai or global drivers.

No push, merge, deployment, live device approval/contribution change or learning run is authorized in this work.
Last read: deployed clone `82c37fc`, all three local lab services stopped. Do not start them just to continue coding.
Native Windows has not been accepted. Avoid Archive writes and never use `/mnt/sekai`; respect current storage rules.
Communicate briefly in Vietnamese. Commit logical groups; keep failures and each evidence folder's limits explicit.
