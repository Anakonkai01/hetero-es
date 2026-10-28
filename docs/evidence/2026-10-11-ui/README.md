# UI, telemetry and packaged desktop evidence

This review covers the redesigned public home/auth flows, lab navigation,
dashboard, fleet/owner devices, resources, models, experiments, generations,
candidates/seeds, events/artifacts, profile and operations, plus Worker/Server.
It preserves historical numerical proof; it does not create a new GPU campaign.

## Verified

- [Verification totals](verification.json): Track A CPU 2,052 passed/100 skipped;
  backend 96 passed; Worker Node 12 passed; Server Node 1 passed. Web lint and all
  three frontend builds passed. The backend warning is an existing Starlette
  test-client deprecation.
- [Live browser review](web-review.json): 52 page/theme/viewport checks, no JS
  exceptions or document overflow. Anonymous auth/session 401 responses are
  expected; no other failed API response occurred. Login/register mobile checks
  explicitly verify an anonymous form, not a signed-in redirect. Candidate seeds
  are visible in actual completed-run ledger data.
- [Desktop renderer fixtures](desktop-states-review.json): 26 cases across both
  themes, each at 1100 and 390 pixels. Covers OFF/active/draining/unknown, pending
  approval, stale/missing telemetry, sign-in/install/pair and Server setup/error/
  online states. Enable contribution is blocked in draining/unknown/pending
  approval cases. **Fixtures are layout/control evidence, not hardware evidence.**
- [Actual portable app rendering](packaged-desktop-review.json): both published
  Linux portable archives were extracted and opened in real Electron with fresh
  isolated user data under Xvfb. Both themes passed, with no JS errors/overflow.
  GPU computation and installation were not enabled by this render review.
- [Actual CPU Server installation](packaged-linux-server.json): fresh hash-verified
  standalone Python/CPU wheels, bootstrap, same-origin Web/API, initially held
  queue, manual start, close-to-tray, confirmed stop/restart and orphan parent-pipe
  shutdown passed. It used isolated data and a randomly generated private test
  password. No Torch, Conda mutation or GPU was required.
- [Migration receipt](migration.json): online backup/trial and held live cutover
  preserved all 21 experiment body/snapshot rows and SQLite integrity. The later
  history-table reload also checked identical rows, owner flags and zero reserves.
- [Final state](final-state.json): real qualified-UUID 5070 Ti telemetry, both
  disk capacities, fresh observation/history, local contribution OFF, dispatch
  held and zero reservations. GPU energy is a session estimate of this GPU's
  sampled power, not whole-computer or per-experiment energy.
- [Downloads](installers.json) and [HTTP checks](download-checks.json): all four
  new Linux/Windows app downloads matched full sizes and SHA-256 over the Web URL.

## Screenshots

[Light home](screenshots/light-home.png), [dark home](screenshots/dark-home.png),
[light login](screenshots/light-login.png), [dark login](screenshots/dark-login.png),
[mobile login](screenshots/dark-mobile-login.png),
[dashboard](screenshots/dark-dashboard.png), [fleet](screenshots/dark-workers.png),
[mobile fleet](screenshots/dark-mobile-workers.png),
[actual experiment history/seeds](screenshots/light-experiment.png).

[Actual packaged Worker](screenshots/packaged-worker-light.png) and
[actual packaged Server](screenshots/packaged-server-dark.png) show fresh setup.
[Paired Worker fixture](screenshots/fixture-worker-active-light.png) and
[running Server fixture](screenshots/fixture-server-online-dark.png) show populated
layouts using an explicitly fictional assignment/lab state; they do not prove
active GPU execution or a running production Server.

Raw logs and additional screenshots are private under
`~/.local/share/heteroes-ui-review`. Scripts `review-product-ui.mjs`,
`review-desktop-states.mjs` and `review-desktop-ui.cjs` reproduce these scoped
reviews. Windows execution of this UI, a normal owner desktop walkthrough, GPU
pause/resume and simultaneous multi-GPU campaigns remain pending. Cloud deferred.
