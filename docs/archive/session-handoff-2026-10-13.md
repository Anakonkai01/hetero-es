# Session handoff — 2026-10-13: r6 prepared, Windows still unverified

**Read this first**, then `session-handoff-2026-10-12-close.md` (what the owner reported) and
`evidence/2026-10-13-r6/README.md` (what was changed and what is NOT shown). Owner rules are unchanged
(`AGENTS.md`): Vietnamese, short, simple; no push/tag, no generated-by trailers; tests first, then a scratch
mutation check; GPU only with `--gpu` + `HETEROES_GPU_ACCEPTANCE=1`.

## State at the end of this session

- Branch `feat/local-first-lf1` in both repos, commits only on this branch, nothing pushed. Code changes are in repo B
  (this repo); repo A (runtime) is unchanged since the r5 close.
- **Live lab (https://lab.heteroes.site): running r5**, unchanged. It was down for a few minutes this morning: the
  machine had rebooted and `/mnt/Archive-2tb` (NTFS, UUID `10443D1F443D094C`) was not mounted, so the Web/API could not
  open its storage. It was mounted again with the same command earlier sessions used
  (`mount -t ntfs-3g -o uid=1000,gid=1000,umask=077,windows_names,norecover,nodev,nosuid /dev/disk/by-uuid/10443D1F443D094C /mnt/Archive-2tb`)
  and `systemctl --user restart heteroes-lab`. This was the first real reboot test of the user unit: the unit itself
  started at login as designed; only the disk was missing.
- **r6 is built and prepared, not published**: `/mnt/Archive-2tb/heteroes-local/downloads/lf1-20261013-r6`,
  receipt `evidence/2026-10-13-r6/installers-r6.json` (`publiclyPublished: false`). The live download page serves r5.
- The backend password rule (8 characters, see below) and the new web UI exist only in the repo and in the r6 Lab
  Server installer; the **live** backend/web are still the r5 ones (12 characters, old pages).

## Needs the owner (nothing here was done without them)

1. **Publish r6?** (`python3 scripts/publish-local-installers.py --packages /mnt/Archive-2tb/heteroes-local/downloads/lf1-20261013-r6 --build lf1-20261013-r6 --receipt docs/evidence/2026-10-13-r6/installers-r6-published.json --prepared-receipt docs/evidence/2026-10-13-r6/installers-r6.json`). It only changes the manifest and links; r5 files stay.
2. **Put the new web UI and backend live?** Build the web, then a managed restart (`local-lab.py restart`, it holds the queue itself and refuses if a run is live). The 8-character password rule starts applying to *new* registrations only.
3. **Mount the Archive disk at boot.** Needs root. Suggested `/etc/fstab` line:
   `UUID=10443D1F443D094C /mnt/Archive-2tb ntfs-3g uid=1000,gid=1000,umask=077,windows_names,norecover,nodev,nosuid,nofail,x-systemd.device-timeout=10 0 0`
   Without it the lab needs a manual mount after every reboot (the unit now retries every 30 s, so it comes up by
   itself once the disk appears). Also still open from last session: `sudo loginctl enable-linger pc5070ti`.
4. **Password policy**: the AI chose 8 characters with a common-password/own-name check (the owner only said 12 felt
   excessive). Say if another number is wanted (`backend/passwords.py::MIN_LENGTH`, `RegisterPage.tsx::MIN_PASSWORD`).

## Next steps

1. Owner runs the **r6 Windows installer** from a fresh state (they have been given the local path; the website
   still offers r5). Ask for: what the red box says (it shows a code such as `LAB_UNREACHABLE`), whether Quit and
   the tray menu now work, and, if anything fails, the file `%APPDATA%\@heteroes\worker\logs\worker.log` (or
   "Export diagnostics"). Do not ask for GPU/runtime steps before the address, sign-in, sign-out and exit work.
2. If Windows still fails, reproduce from `worker.log` first; add a failing test; fix; build a NEW immutable name (r7).
3. Only then: runtime install, GPU check, pairing, two-machine/public-route tests (owner authorisation needed).
4. Remaining feedback not yet touched: the Worker/Web visual polish beyond these changes, and the backlog in
   `session-handoff-2026-10-12-close.md` (identity/epoch, export/restore, graphical network setup).

## Tools added

- `scripts/check-worker-onboarding.cjs` — Electron contract (add `--packaged <exe>` for a built app); Linux only.
- `scripts/check-web-onboarding.mjs` + `scripts/serve-test-lab.py` — Chromium contract against a throwaway CPU lab.
- `scripts/build-apps.sh` now writes `desktop/worker/resources/defaults.json` (offered lab address, build name):
  `DEFAULT_LAB_URL` overrides the address; commit the file after a build.
- `local-lab.py` refuses to start/restart when the pinned storage disk is not mounted, and says which one.
