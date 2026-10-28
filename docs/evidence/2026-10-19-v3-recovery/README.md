# Complete Recipe v3 recovery state — 2026-10-19

Implementation `c033fe8`; download CLI correction `d05503d`. No frozen numerical,
ledger, generation-record or worker-API source changed. No lab state changed.

## Behavior and acceptance

Manifest format 2 carries a bounded v3 state object (recipe, plan, dataset,
selection, validation history and audit restore faults), pinned initial adapter,
selected weights and canonical ledger/parent/child files. Validation binds those
objects to recipe/plan/dataset identities and rejects missing selection instead
of silently resetting it. Format-1 legacy recovery remains accepted.

Replacement restore rebinds dataset/model-manifest paths, restores validation and
best weights, rebuilds metrics with test locked and holds dispatch. The operator
provides the same pinned base model at the installation's private path; verified
preparation checks its bytes. Credentials, processes and previous export receipts
are not restored. The download CLI accepts the new allowlisted names and checks
manifest metadata before downloading.

- `check-all.log`: **22/22 ALL PASS** in a detached checkout at `912b35e`;
  **2,269 passed / 100 skipped** runtime, **302 passed** backend. This predates
  the download-CLI fix; the final combined check at `e35811c` in the NEW
  `../2026-10-19-v3-sdk/check-all.log` covers that fix and all subsequent CLI work:
  **22/22, 2,273 passed / 100 skipped, 302 backend passed**.
- `integration-second.log`: **14 passed**. Full and LoRA run through the real
  managed runner and worker subprocesses over HTTP. A generation-0 point is saved,
  the original run directory deleted, and the restored installation resumes with
  a separately provisioned model path. Both final hashes, retained selection and
  independently reloaded export match the uninterrupted run.
- Separate state tests use distinct synthetic parent/child/earlier-best bytes to
  prove the earlier selection survives even when it is neither current checkpoint.
  They also check initial adapter, history, audit faults and plan-drift rejection.
- `download-final.log`: the real restore CLI against a mocked download service
  restores a complete v3 point and retains selection. No real remote object store
  is contacted by this test.
- `backend-tests.log`: **10 passed**, object manifest/deduplication/safe paths and
  the packaged CPU-only server's import closure. `mutation.log`: **5/5** killed;
  no equivalent survivors.

## Intermediate receipts

`tests-first.log` fails against the old incomplete format. `integration.log` was
invoked from the repository root instead of runtime/: five worker subprocesses
could not locate scripts/run_worker.py (exit 2). The corrected working directory
passes all 14 tests in integration-second.log. `download-first.log` exposes the
remaining format-1-only path check in the downloader; download-final.log verifies
its repair. None of those failures are represented as acceptance.

## What this does NOT show

CPU fixture recovery only, not a real remote object-store disaster, Windows or
installer acceptance, a deployed lab, or learning benefit. The tiny managed runs
can have constant rewards/no-op updates; nonzero numerical updates are exercised
separately by the v3 local audit test and Qwen GPU qualification. The model's base
files are intentionally not duplicated into each recovery point. Restore requires
those exact files to be provisioned again and dispatch to be explicitly resumed.
Very large validation history can exceed the bounded state object; capture then
reports a recovery failure while numerical computation retains its existing policy.
