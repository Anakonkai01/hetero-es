# Candidate14: deterministic CPU noise and product UX

Owner-approved work from `96182b7`, branch `feat/real-user-c13`. CPU V2 first;
CUDA enablement and chunk 128 deferred. The owner requested handoff to Claude
at 15% remaining usage. Claude finished the native approval fix (candidate14e) and close-out on 23 Oct.
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

## Native approval defect: fixed in candidate14e (23 Oct, Claude)

Candidate14d kept `device.approvalStatus=PENDING` from pairing while signed out,
although the live device was APPROVED. `native-c14e/before-click-off-14d.json`
and `before-off-14d.png` record the real defect: after OFF, the switch was
disabled with "Waiting for administrator approval".

`6ad540d`: signed out, the Desktop reads `/api/v1/device/summary` with the
device token; a rejected token shows REVOKED, an outage keeps the last value, and
only durable device fields are saved. The lab still authorizes every change.
Tests were red first; `checks-c14e/` has Worker unit (all pass), Prettier,
types, build, Electron onboarding/station, and 8/8 killed mutants.
`build-apps-c14e.log`, `packaged-worker-install-c14e/`: candidate14e build and
packaged Linux install check. The Worker runtime archive is unchanged (C/D SHA).
Installers were first published by mistake into the working tree's ignored
`frontend/public/downloads` (`installers-published-e-worktree-only.*`, removed;
the live lab was not changed by it), then published on the live lab with the
deployed app's script (`installers-published-e.*`); the public downloads match
the prepared hashes (`installers-public-download-e.txt`).

Native D→E upgrade on Thao (`native-c14e/`): RPC quit, silent install with the
prepared hash, then signed out: APPROVED, OFF switch enabled, a real click turns
it ON (`after-click-on-14e.json`, `station-on-14e.png`), and the lab reports
ONLINE/ON (`lab-thao-after-on.json`). Actual OS telemetry (process/disk/network
lists reduced to counts) is in `windows-telemetry-14e.json`; CPU power/temperature
are reported as unsupported with a reason. Final relaunch is a normal launch in
the console session without debug ports (`relaunch-normal.ps1`), switched ON by
UI Automation (`uia-enable.ps1`), lab ONLINE/ON
(`lab-thao-on-after-normal-relaunch.log`). Real lab run page and Live/replay tab
at 1440/768/375 px: no horizontal overflow and no console errors
(`web-final-c14e/`).

Close-out: nhut's exact temporary public-only rule was removed and its absence
recorded, `~/f13-diag` and own replay/probe folders deleted
(`nhut-firewall-removed.log`); own Windows temporary folders and installers
deleted (`native-c14e/windows-temp-cleanup.log`).

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
The candidate14e native fix was accepted on one Windows machine signed out with
an APPROVED device; PENDING/REVOKED/outage paths are covered by unit tests and
mutants, not by a real revoked device. No account sign-in UI change was made.
