# Handoff — v3 product integration, 2026-10-19

Read `../AGENTS.md`, `HANDOFF.md` and `handoff-v3-extensibility.md` first. The original handoff/evidence remains unchanged. This follow-up records the continuation from `a804eac`.

## Branch and scope

Working branch: `feat/v3-product-integration`, created from `feat/extensibility-step0` at `a804eac`. No push, tag, merge, GPU computation, SSH, live-lab operation or device approval/contribution change. Existing environments and published desktop profiles are unchanged.

Commits:

- `c9eccfd`: managed runner/worker/agent v3 integration; pinned initial LoRA transfer and retention.
- `ae96728`: validation selection, metrics/events and verified full/subset/PEFT export.
- `7819b09`: backend, qualification fences, arbitrary-column assets, wizard/templates/metrics, Vietnamese strings and browser contract.
- `6aa95b5`: regression repair for selected-model revision in draft headers and complete replacement of recipe settings when a draft changes format.
- `5e12ad4`: documentation and intermediate/final evidence snapshots.
- A follow-up receipt commit adds the complete last desktop probe and erratum; see `evidence/2026-10-19-v3-web-final/README.md`.

## Completed work

Original handoff steps 1–3 are implemented and CPU-checked. Product config adapts to `v3.run.build_documents`; shared-lab plans use declarative scorers only. The worker CLI independently rebuilds its recipe from verified model/data and the transferred initial adapter, then returns texts. The coordinator scores and commits them with schema-6 ledger and record-v2 updates. Full/subset/LoRA, antithetic choice, nullable system prompt and `zscore@1` reach the product runner through frozen assignments.

`heteroes.v3.tracker.Tracker` evaluates validation with the frozen scorer, selects highest reward/earliest tie, retains selected weights and binds selection to both recipe and plan. It records the initial, interval and final validations. Test runs only at final export after worker shutdown; an independent reload must reproduce selected trainable weights, raw test outputs and scores. Failed reloads do not publish verified metrics. Product projections and web tables/events expose validation history.

The backend remains NumPy/Torch-free. `v3/data.py`, `v3/options.py`, `v3/scoring.py` and canonical serialization are explicitly shipped in the Lab Server subset. `v3/options.py` is the shared weight-space/rule validator, also used by recipe documents. No protected numerical/protocol file changed.

The browser contract now imports v3 arbitrary columns and creates/inspects a LoRA/antithetic/declarative-scorer draft against a disposable fixture lab. Its model files and device compatibility declaration are synthetic; real CPU coordinator/worker execution is tested separately with offline tiny Qwen2 models. The fixture lab has disposable local object storage. Do not copy synthetic qualification declarations into a real lab.

User flow and limits: `runtime/docs/v3-product-runs.md`.

## Evidence and checks

Each step has a NEW immutable-after-commit evidence folder with limits and intermediate failures:

- `evidence/2026-10-19-v3-product-runner`: final 22/22, runtime 2,241 passed / 100 skipped, backend 287 passed; 6/6 mutants killed. Final check used detached `c9eccfd`.
- `evidence/2026-10-19-v3-validation`: 22/22, runtime 2,248 passed / 100 skipped, backend 287 passed; 6/6 mutants killed. Check used detached `ae96728`.
- `evidence/2026-10-19-v3-web-final`: authoritative **22/22** completion log and hashes of all individual step logs (the preceding `v3-web` folder holds the other step logs and mutation receipts). Runtime **2,252 passed / 100 skipped**; complete backend rerun after the final repair **299 passed**. The earlier check-all backend collection had 298 tests. 8 backend + 3 frontend mutants killed, plus 2 draft-regression mutants. No equivalent survivors. The final full browser probe checks the repaired model revision.

The main checkout advanced while step-specific checks ran in detached checkouts; shared ports were serialized. Initial checks failed on test imports, unsupported test rule, exact browser labels or fixture reuse; all are preserved and explained in the READMEs. Fixture authentication in failed tracebacks is redacted. The last two draft regressions were caught with explicit failing tests before repair. The first web evidence commit preceded completion of its last desktop probe; its partial log is preserved unchanged, and `v3-web-final` contains the complete 22/22 receipt and explicit erratum.

## Next work and concrete limits

Continue the original plan at step 4: deterministic audit scheduling, then r11/real Windows qualification (step 5), the owner's flag day (6), authorized GPU and preregistered experiments (7), SDK polish (8). Do not remove v1/v2 RUN paths, advertise a deployable r11 release or infer GPU/Windows/learning acceptance from these CPU checks. The source supports v1/v2 alongside staged v3 until the owner chooses the switch; no transition release was published.

Before the flag day, extend and qualify v3 disaster recovery: the existing recovery manifest permits only ledger/config/identity and parent/child weights. It does not carry recipe/plan, the pinned initial adapter, earlier best-selection weights or validation history. This workstream checks in-place restart and selected export, not a complete restore onto a replacement installation. Such a restore must not silently rebuild selection from only the last checkpoint.

A cold LoRA worker needs a private bulk route for its initial adapter. Public replay-only operation can reuse a verified cached adapter; it does not bypass the private-file transport restriction. No live state was queried or altered by this continuation.
