# Plan: professional Windows installer ("Part B"), for the next session

Status 2026-10-14: **not started** (the owner chose to do it next session). Decisions already made with the owner: step-by-step
wizard installer (vi + en), no code signing yet (a "what Windows will ask" guide + SHA-256 instead).
Done in r10 already: the Worker uninstall deletes its data folder (`desktop/worker/build/installer.nsh`, `deleteAppDataOnUninstall: true`).
Keep that behaviour: never wipe data on an in-place upgrade, never for the Lab Server. Test installs in a scratch Wine prefix
(rename Wine's PowerShell stub first, see the 2026-10-14 handoff). Repo rules: tests first, mutation check, no push, no Co-Authored-By.

## Part B — Professional installer (r9, after the owner retests r8; or merged into r8 if the cause is trivial)

Findings: `desktop/{worker,server}/package.json` use `nsis.oneClick: true`, a flat 1-image `icon.ico` (letter "H" on teal)
and no installer images; `frontend/static/favicon.svg` is still the Vite template logo. `makensis`, `wine` and
`rsvg-convert` are installed locally, so assets can be generated reproducibly.

1. **Brand assets** (new `desktop/brand/`): one SVG mark + wordmark (teal, matching the web UI tokens in
   `packages/product-ui`), a script `scripts/make-brand-assets.sh` (rsvg-convert → PNG; multi-size ICO 16/24/32/48/64/128/256;
   NSIS `installerSidebar` 164×314 BMP, `installerHeader` 150×57 BMP, tray icon, Linux icon). Worker and Lab Server get
   related but distinguishable marks (same shape, different accent/badge). Replace the Vite favicon on the web too.
2. **Wizard config** (both apps' `package.json` → `nsis`): `oneClick:false`, `allowToChangeInstallationDirectory:true`,
   `perMachine:false` (no admin prompt), `createDesktopShortcut`, `createStartMenuShortcut`, `runAfterFinish:true`,
   `shortcutName`, `uninstallDisplayName`, `installerIcon/uninstallerIcon/installerHeaderIcon`, `license` (EN+VI text file),
   `installerLanguages`/`language` with an English+Vietnamese string include (`build/installer.nsh`) for Welcome/Finish pages.
   Keep `deleteAppDataOnUninstall:false` (device credential safety) and say so on the uninstall page.
3. **Windows metadata**: `win.publisherName`, `legalTrademarks`, file version/product version from the build name,
   `extraMetadata.author`, so the file Properties → Details tab and SmartScreen show "HeteroES Lab", not blanks.
4. **First-run polish**: tray + window icons from the new assets; `defaults.json` already pre-fills the lab URL; add the
   build name to the footer (exists) and an "About" line.
5. **Download page + guide**: on the lab's download page add a short "Windows will ask…" guide (SmartScreen → *More info* →
   *Run anyway*; why: unsigned), SHA-256 with a copy button and a PowerShell one-liner, screenshots of each wizard page.
   Leave a documented, empty signing hook (`CSC_LINK`/`CSC_KEY_PASSWORD` env, `win.signtoolOptions`) in the build script —
   nothing signs until the owner buys a certificate.
6. **Verification without a Windows PC**: build through Wine, run the NSIS silent install in Wine
   (`/S`, `/D=`) and the packaged probes; capture wizard screenshots by running the installer under Xvfb+Wine; check
   ICO contains all sizes (`identify`), file properties via `wine reg`/`exiftool`. State plainly that Windows rendering
   (DPI, SmartScreen, shortcuts) is unverified until the owner installs it.

