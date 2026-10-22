# Candidate14: deterministic CPU noise and product UX

Owner-approved work from `96182b7`, branch `feat/real-user-c13`. CPU V2 first;
CUDA enablement and chunk 128 deferred. The owner requested handoff to Claude
at 15% remaining usage. **Not final product acceptance; not pushed/merged.**
See [current handoff](../../handoff-2026-10-22-candidate14-claude-next.md).

## Implemented and deployed

- `4c0e166`: integer-only V2, generated/pinned thresholds, engine-bound device
  and model qualification, V1-preserving plumbing, persistent per-run block and
  one explicit retry, historical identity snapshots, own-access guards, real OS
  telemetry and missing reasons. ADR-011/numerical contract section 18 apply.
- `083fbfa`: DOCX home/install, account menu, compact resource metrics, themed
  keyboard search/select, ten-item dataset/artifact pagination, Live/replay
  controls, machine/GPU identities, responsive layouts and translations.
- `299dcbe`: notebook qualification/cache bound to requested engine.
  `937c48a`: paired Worker ON without an account session, with no broader
  credential fallback after authorization failures.
- Live lab: `f70b05f`, candidate14c. Published installers: candidate14d. Linux
  CLI: C; native Windows: D. C/D numerical runtime archive SHA is
  `630ff292d0c6bb18a4ce87505d62a485ef42a44cae1aa4cb973f01588d4cea2c`.
  Backups and deployments are recorded; lab changes used `local-lab.py`.

## Verification

- `checks-final-progress.log`: full combined ALL PASS before final SDK/ON
  refinements. Runtime 2664 passed/102 skipped, backend 437 passed; all other
  lint/format/i18n/import/unit/type/browser/Electron steps passed.
- `checks-release/`: all steps except worker-unit passed. That step read new red
  tests while the native fix was being implemented; its final targeted rerun
  `worker-unit-final.log` is **92 passed**. Do not call the release log ALL PASS.
  Later SDK, desktop, build/type/i18n receipts cover the final changes.
- Final scratch mutation checks: six runtime, six backend, two SDK and two
  device opt-in mutants killed; controls pass. Intermediate failures retained.
- V1 fingerprints retained; threshold regeneration byte-identical. Source GPU
  probes across glibc 2.43, glibc 2.39 and native Windows match full/LoRA
  positive/negative, exact restore, perturb and update hashes:
  `source-gpu-parity.json`. Final installed CPU runtime boundary/golden/update
  and portable source identity match: `installed-parity.json`.
- `windows-installed-final-selftest.json`: final packaged native GPU self-test.
  `windows-installed-final-status.json`: D, signed out, agent enabled/ONLINE.
- `interaction-fifth/receipt.json`: keyboard, pagination/search, own-account
  guards and no overflow at 375/768/1440. Initial screenshots in `visual-first/`
  retain a mobile artifact overflow, fixed before the final interaction test.
  Fixture all-page/live/onboarding/Electron suites also passed.
- Isolated Worker/Server package install, GPU qualification, import/lifecycle
  checks passed. SDK is built before Server capture; package receipts record
  source closure. Single exploratory whole-model timing samples show V2 update
  slower than V1; no speedup is claimed.
- Real run `2dd6e2f78aa84e60aa5bafaed3fe2c6b`: declared before submission in
  `acceptance-plan.md`, notebook SDK path, Linux + native Windows, nhut public
  only. `live-final.json`, `live-results.json`, `live-ledger-counts.json`:
  **10 updates, 80 completions, 3/3 audits matched, no worker blocks**, all three
  devices contributed. `live-after-run-workers.json`: all reservations released.
  Independent replay on both Linux hosts matches **10/10 child hashes**,
  with nonzero updates (`managed-replay-summary.json`); no candidate text
  regeneration is claimed.

## Open native UI defect and intermediate receipts

Native D's cached `device.approvalStatus` remains PENDING when signed out,
although the live device is APPROVED and actually contributes. Service ON works,
but the UI can block the next OFF-to-ON action. Fix and packaged/native UI
acceptance remain; complete native user-journey acceptance is not claimed.

Candidate14/B/C/D retain successive fixes: Server SDK capture, engine-aware
qualification, paired local ON. Failed red tests, fixture selector/timing
assertions and mutation controls are preserved next to passing reruns. Native
PowerShell GUI wrappers sometimes waited for the child GUI tree or misreported
LASTEXITCODE. The first installed CPU wrapper checked READY instead of
READY.json; the second produced a successful native JSON but its wrapper still
reported failure. The actual JSON is compared in `installed-parity.json`.

## What this does NOT show

No new ES algorithm, learning proof or enabled CUDA noise engine. V2 is a finite
quantized Gaussian law, not an exact continuous Gaussian. Historical V1 libm
behavior remains immutable; old runs are not migrated. Persistent worker
blocking is the owner's **temporary** workaround, not public weight recovery.
Fixture UI checks do not prove every OS sensor or the complete native journey.
Managed acceptance does not prove every real restart/retry scenario. Final live
screenshots, native UI repair, diagnostic cleanup and push/FF are outstanding
unless explicitly closed in the current handoff.
