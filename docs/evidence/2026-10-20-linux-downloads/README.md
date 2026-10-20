# Linux CLI download wiring — unfinished checkpoint (2026-10-20)

The build now generates the headless CLI bundle alongside refreshed desktop resources. Installer preparation includes
verified CLI script/bundle hashes in an optional linuxWorker manifest object, preserves app-only historical builds and
checks reviewed CLI bytes before publication. Private-transfer manifests rewrite both CLI URLs to the bulk address.
The publisher supports a stable install-worker.sh alias and immutable versioned bundle names.

`before.log` records failing tests before implementation. `after.log` has 8 passing installer/web tests, including a real
synthetic one-line install, checksum rejection and refusal to publish changed CLI bytes. `checkpoint-final.log` includes
backend option/usage tests after formatting. Only synthetic temporary publication is exercised by tests; no real links
or public manifest have changed.

## What this does NOT show

**The frontend download page is NOT wired yet.** Add a reusable Linux CLI section with a copyable one-line curl command
in InstallerDownloads, GetStartedPage and LabDevices, using the server-provided installer URL (private-transfer aware).
Add translations and meaningful browser coverage. Mutation coverage of new publisher/routing behavior is still pending.
No final candidate3 build, real publication, public availability or r11 installer acceptance is claimed.
Review preflight ordering and atomic alias/manifest replacement, especially failures and an existing previous-build alias.
