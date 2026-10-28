# Frozen audit coverage through SDK, API and UI (2026-10-25)

Base: `5c5ae49`, branch `fix/human-review-single-model-2026-10-24`. Owner requested continuation of the full approved
human-review plan, then explicitly closed the session to conserve usage. This is the completed audit-rate slice of M2.

## Change

- `ESConfig.audit_rate` and the local/distributed/managed paths carry `auditRate` in [0,1], default .05, including
  explicit zero. Booleans, strings, null and nonfinite/out-of-range values are rejected. CLI overrides are resolved
  before run creation; managed CLI submissions can carry the setting too.
- `audit-config.json` pins the operational setting beside a run. Restart refuses a different or invalid saved setting.
  Model/recipe/plan/update identities exclude coverage: a real tiny-model CPU comparison at rates 0 and 1 has identical
  recipe bytes, plan bytes, update record and final child weights. This does not add audit settings to historical recipes.
- Backend request/template validation, optional v3 command forwarding, frontend templates and the experiment form
  preserve zero. The UI shows percentages, default 5; browser coverage checks 29, 100 and a saved draft at 0.
  Non-v3 product configurations still strip v3-only fields. Previously saved v3 configurations may omit auditRate.
- The hash selection rule is shared by the runtime and read-only backend view. Historical managed default .05 keeps
  the exact `2**256 // 20` threshold. Backend reporting now uses the run's saved rate instead of always assuming 5%.
- The current audit completion states and legacy three-mismatch quarantine policy are unchanged by this slice.

## Receipts

- `runtime-red-01.log`, `backend-red-01.log`, `frontend-red-01.log`, `view-red-01.log` preserve reproductions.
- `runtime-green-01.log`: 31 passed. `runtime-green-02.log`: 58 passed across controls, audit, SDK, local/distributed
  CLI and agent lab CLI. The final mutation control additionally covers the newly added exact hash-boundary cases.
- `backend-green-01.log`: 45 passed; `backend-green-02.log`: 66 passed, one dependency deprecation warning.
- `frontend-green-01.log`, `types-01.log`, `i18n-01.log`: template units, TypeScript and translation checks passed.
- `runtime-mutation-01.log`: control 18 passed, **8/8 killed**; covers zero forwarding, invalid bools, frozen settings,
  invalid saved settings and exact default hash boundaries.
- `backend-mutation-01.log`: no tests selected because the initial -k expression was wrong; not an acceptance run.
  `backend-mutation-02.log`: control 15 passed, **4/4 killed** (strict request types, zero in templates, command
  forwarding and rate-aware reporting).
- `frontend-mutation-01.log`: **2/2 killed**, covering omitted rate and lost zero in copied templates.
- `browser-01.log`, `browser-01/`: complete experiment-tools Chromium contract against a temporary fixture lab,
  including default percentage, percent entry and a saved v3 draft with auditRate zero. The fixture server terminated.
  Its fake device approval is fixture setup, not an operation on an enrolled/live device.
- `lint-01.log`, `format-01.log`, `web-build-01.log`: Python lint/format and source UI build passed.

## What this does NOT show

No full check-all/runtime/backend matrix was rerun after this slice: the last complete runtime/backend result is
2,848 passed/186 skipped and 439 passed at `5c5ae49`, before these audit-control changes. The receipts above are the
new slice's targeted checks, mutations and browser acceptance. No GPU, native Windows, production deployment,
learning run, push/merge or device approval/contribution change occurred here.

Detailed audit states (matched/mismatched/timed-out/skipped), strict first-mismatch stop with preserved evidence,
stage/progress watchdogs and D10 restore recovery remain open in M2. M3, strict throughput work, M4–M6 remain in scope.
Concurrent controller ownership and crash/power-loss acceptance of operational configuration are not demonstrated here.
