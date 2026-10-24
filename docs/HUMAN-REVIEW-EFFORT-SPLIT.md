# Human-review work by reasoning effort

Owner instruction, 2026-10-25: resume from clean `2776e88`, use this xhigh session for difficult work, and leave
straightforward work to a later session at lower effort. The approved M0–M6 plan remains the source of scope:
`/home/pc5070ti/projects/heteroes-review-2026-10-24/PLAN-SUA-HUMAN-REVIEW.md`.
No push, merge, deployment, live device change or learning run is included.

## This xhigh session

1. M2 audit accounting: canonical candidate outcomes, durable drain closure, restart and late-result races.
   Preserve historical sampling and three-mismatch ledger behavior, and keep `audit_counts()` compatibility.
2. M2 safety: a shared run-level guard across generation API rotation, serialized update admission, persisted faults,
   and a strict first-mismatch primitive retaining both execution receipts. Strict activation stays behind M4's real
   backend/recipe identity and qualification gates; an internal fixture does not make the current recipe strict.
3. Adversarial tests, scratch mutations and CPU integration checks for these core changes. Record precise limits.

## Next lower-effort session: bounded product work

Recommended **medium** effort for the first connected slice; **low** for isolated copy/documentation follow-ups.
Read the new handoff before changing anything; these are follow-ups after the core contracts are committed.

| Task | Concrete completion gate |
| --- | --- |
| Project detailed audit outcomes through supervisor/backend/types | Read canonical ledger outcomes and durable per-generation drain reasons; count candidates once; preserve `completed`/`mismatches` API compatibility. Never derive matches from missing events. Mark old or missing operational evidence unknown. |
| Audit UI and translations | Explicit disabled, pending, matched, mismatched, timed-out and skipped labels. Zero selected is not evidence of successful checking. Cover zero rate, no auditor, timeout and historical partial data with fixture browser checks. |
| CLI/help and examples for existing audit controls | Preserve explicit zero, frozen coverage and historical identities. Document that mid-run coverage changes are unsupported. |
| Routine receipt indexing and package reruns | Link the exact commits/checks; preserve failures and platform limits. Rerun packages after code changes that affect runtime contents. No native Windows claim from Linux source packages. |

Do not turn a low/medium-effort session into an unplanned numerical or recovery redesign. Use the committed
contracts; if a new cross-component invariant is uncovered, record it for the next heavy slice.

## Heavy work still in the full plan

These are **not** reassigned to low effort just because they remain after this session:

- M2 D11: meaningful progress by compute/sync/delivery/scoring/audit/update/recovery stage; monotonic deadlines,
  restart semantics and finite operator/researcher hard caps. Heartbeats must not refresh progress deadlines.
- M2 D10: persisted once-per-worker/run recovery budget; canonical reload, self-test/restore/probation and boundary
  rejoin, reconciling local poison, ledger/audit quarantine and supervisor state without device approval changes.
- M3: bounded recovery streaming/backoff, safe verification caching, retention dependency graph and measured
  early/middle/late bookkeeping. Carry the new audit drain/stop sidecars and reconcile faults later than an immutable
  recovery snapshot; replacement recovery does not yet preserve this strict guard. Real full-disk acceptance remains deferred.
- M1: exact arithmetic while caching RoPE, reducing launch cost and batching rows/sequences; cross-GPU token and
  native baseline/performance evidence. Existing SGLang/vLLM results do not replace these gates.
- M4: real backend/recipe identity and qualification namespaces, managed physical-GPU ownership, lifecycle and
  native packaging. Connect strict mismatch activation only here, with a supported qualified identity.
- M0 broader measurements, M5 full system acceptance and M6 frozen quantized base plus ES LoRA remain open.

The scheduling split changes the order of work within the approved plan. It does not mark M2, any untouched
milestone, or the overall objective complete.
