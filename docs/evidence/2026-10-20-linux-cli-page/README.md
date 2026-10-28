# Linux CLI download page and publisher hardening (2026-10-20, session 5)

Finishes the WIP in `2026-10-20-linux-downloads/`. The web app now shows a copyable one-line headless install on the
landing downloads card, Get started (step 2) and Workers → Add a GPU computer, built from the server manifest's
`linuxWorker.installer.url`. The command is
`curl -fsSL '<installer>' | HETEROES_DOWNLOADS='<same directory>' bash`, so the bundle comes from the same place as the
script (a self-hosted lab, or the private LAN/Tailscale address when transfers must stay private) rather than the public
address baked into the script. Addresses that are not plain http(s) or that need shell quoting are never shown; builds
without `linuxWorker` show nothing new.

Publisher (`scripts/publish-local-installers.py`) review fixes:

- every desktop/bundle link conflict is checked before any link, the stable `install-worker.sh` alias or the manifest
  changes, so a refused publication leaves the previous one-line installer and manifest untouched (before: the alias
  switched first, then a later conflict aborted with the manifest still describing the previous build);
- a stale `install-worker.sh.pending` from an interrupted attempt no longer blocks publication;
- publishing (or rolling back to) an app-only build removes the alias instead of offering another build's CLI;
- previous versioned bundles stay linked for scripts already handed out.

Receipts: `unit-before.log` (missing module), `publisher-before.log` (stale pending alias crash),
`publisher-rollback-before.log` (alias kept after app-only publication), `web-onboarding/` then
`web-onboarding-final/` (Chromium fixture lab with screenshots; final has the Linux block after the app address),
`backend-final.log`, `unit-final.log`. `run-web-onboarding.sh` is the helper used.

Mutation checks (scratch copies): frontend 4/4 (`mutation-frontend-final.log`; the first run, `mutation-frontend.log`,
had an ftp:// survivor, fixed by a test case); publisher/private-route 6/6 (`mutation-publisher.log`); file-backed
evaluation identity 2/2 (`mutation-eval-final.log`). `mutation-eval-dishonest-mutant.log` is a first run whose
second mutant was mis-written (always false); the honest "check splitHashes only" mutant then SURVIVED (that log was
removed by mistake before being kept; the survivor is why the test now also rejects a document with the same split files
but a different splitSeed/contentHash).

## What this does NOT show

- No real build, publication, public manifest or live download changed; publication is tested only on synthetic files.
- The one-line install itself was not re-run on a real machine here (the 2026-10-20 headless-worker evidence covers an
  earlier build); the final candidate3 CLI still needs packaged acceptance.
- The copy button's clipboard write is not exercised (headless Chromium); only the displayed text is checked.
- Alias switch and manifest replacement are two separate atomic renames: a crash between them leaves a new script with
  the previous manifest for that moment. Both are individually atomic; the bundle each script names stays downloadable.
