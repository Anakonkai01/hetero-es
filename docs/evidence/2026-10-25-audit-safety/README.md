# Audit outcomes and run safety across generation rotation (2026-10-25)

Base: `2776e88`, branch `fix/human-review-single-model-2026-10-24`. The owner resumed work and asked to prioritize
difficult core work in this xhigh session, leaving straightforward product work for a later lower-effort session.
The complete approved M0–M6 plan remains in scope; M2 is not complete.

## Changes

- Canonical audit outcomes count selected candidates once and distinguish completed/matched/mismatched from pending,
  timed-out and skipped. Disabled coverage is explicit. Any canonical mismatch wins if several auditors have rows;
  missing execution evidence never becomes a match. `audit_counts()` compatibility is preserved.
- Per-generation drain closure is saved beside the run, validated on reopen, and stops new audit admission after
  closure. An accepted late result supersedes an incomplete disposition without rewriting historical rewards.
- Generation APIs share a bounded private lease registry and audit-only lock. Valid older audit results and restore
  faults can arrive through the new generation HTTP endpoint. At capacity unfinished deliveries are retained;
  no new audit is leased until a terminal entry can be evicted. Incomplete coverage remains visible.
- A shared run guard serializes fault observation with write-ahead update admission. Audit restore faults remain
  stopped after reopening state. A failed fault write is retried before the terminal quarantine response.
- An internal strict primitive retains both text receipts and latches the first mismatch before audit commit/ACK.
  A saved stop is honored even by a caller requesting historical policy. The coordinator's current managed recipe
  keeps historical mismatch policy; no SDK/API/CLI strict option or default promotion was introduced.

Full semantics and limitations: [runtime contract](../../../runtime/docs/audit-state-v1.md).
The new source/test bytes and unchanged frozen numerical paths are recorded in `source-identity-01.json`.

## Verification

- `check-all-01.log`, `checks-01/`: **ALL PASS** for the final source. Runtime CPU **2,900 passed, 186 skipped**;
  backend **452 passed**, one existing Starlette/httpx deprecation warning. Includes lint/format, source archives,
  web/desktop units/types/i18n/builds, fixture browser contracts and Electron onboarding/station checks.
- `states-mutation-03.log`: final-source control **10 passed**, **10/10 killed** using `states-mutants-02.json`.
- `guard-mutation-02.log`: final-source control **24 passed**, **17/17 killed** using `guard-mutants-02.json`.
  Includes both admission orderings, post-check fault injection at the real coordinator boundary, old-lease delivery
  through a rotated HTTP server, saved-receipt corruption and bounded retention without discarding unfinished work.
- `packages-01.log`, `packages-receipt-01.json`: fresh Linux source-copy packaging and shared-module imports passed.
  `packaged-guard-import-01.log` imports the new guard from that copy, verifies exact source bytes and confirms that
  the import does not load Torch. The ignored package workspace is `.scratch/audit-safety-linux-20261025`.
- `verification-overview-01.json` indexes final results. `lab-status-01.log` and `deployment-head-01.log` are read-only
  observations: deployment `82c37fca`, all three lab services stopped. No lab operation was performed.

## Retained intermediate failures

- `states-red-01.log`: missing outcome/drain interface. `states-red-02.log`: null saved state was initially ignored.
- `guard-red-01.log`: missing guard module. `guard-red-02.log`: direct invalid receipt and restore-fault retry gaps.
  `guard-red-03.log`: older deliveries were initially refused by the new endpoint and retention was not bounded.
- `states-green-01.log`, `guard-green-01.log`, `targeted-green-01.log`, `targeted-green-02.log` are intermediate
  targeted checks (46, 29, 67 and 56 passed), not a substitute for the final full suite above.
- `states-mutation-01.log` stopped after two kills because one replacement matched two source locations. The revised
  manifest is `states-mutants-02.json`; `states-mutation-02.log` was 10/10 before the shared-guard integration, and
  `states-mutation-03.log` reruns it against final code.
- `guard-mutation-01.log` killed 13/14: removing observation locking survived because an API property acquired the
  same guard lock first. The strengthened reverse-order test calls the primitive directly and detects the missing
  serialization. The final 17/17 receipt includes that test and the later delivery/retention mutations.

## Reproduction

From the repository root, use fresh output/scratch names:

```bash
scripts/check-all.sh docs/evidence/YYYY-MM-DD-audit-safety/checks
python3 scripts/mutation-check.py --repo runtime --copy src --copy tests \
  --env PYTHONPATH=src --env CUDA_VISIBLE_DEVICES= \
  --test '/home/pc5070ti/miniforge3/envs/heteroes-match/bin/python -m pytest -q tests/v3/test_audit_guard.py tests/v3/test_audit_guard_integration.py' \
  --scratch .scratch --mutants docs/evidence/2026-10-25-audit-safety/guard-mutants-02.json
python3 scripts/mutation-check.py --repo runtime --copy src --copy tests \
  --env PYTHONPATH=src --env CUDA_VISIBLE_DEVICES= \
  --test '/home/pc5070ti/miniforge3/envs/heteroes-match/bin/python -m pytest -q tests/v3/test_audit_states.py' \
  --scratch .scratch --mutants docs/evidence/2026-10-25-audit-safety/states-mutants-02.json
scripts/build-apps.sh --check .scratch/fresh-audit-safety-linux
```

## What this does NOT show

No GPU/remote/Windows acceptance, new inference equality or learning result, push, merge, deployment, device approval
or contribution change. The browser/Electron checks exercise existing fixture product contracts; the new detailed
audit projection and labels are reserved for the next medium-effort session.

Reopen tests reconstruct independent guard/API objects from successful writes; no hard-kill or power-loss acceptance
was run. A failed write stops the current process and its retry is tested, but immediate process loss before a
successful retry is not a durable-stop guarantee. Directory-fsync and real full-disk acceptance remain open.

The private in-memory audit lease registry is bounded and shared across generation rotation, not persisted through
coordinator restart. Missing eventual reports remain incomplete coverage. Multiple coordinator writers are not
accepted. Strict receipts store text/hash and leased chunk, not token IDs, backend/build attestation or proof of
which worker is correct. Historical three-mismatch quarantine and numerical identities remain unchanged.

Existing recovery points carry audit restore faults, but not the new drain/stop sidecars; replacement-installation
recovery does not yet preserve this strict stop or reconcile faults newer than an immutable snapshot. M3/M4/M5 must
close those dependencies and storage/identity gates before strict managed activation. D10 automatic restore recovery,
stage/progress watchdogs, explicit hard caps, strict throughput work and the rest of M0–M6 remain open.
