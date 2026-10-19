# Session close — 2026-10-12: public r5, Windows onboarding blocked

**Read this first in the next Claude/Codex session.** Then read
`session-handoff-2026-10-12-lf1.md` for owner rules/decisions, and
`session-handoff-2026-10-12-codex.md` for implementation and earlier CPU evidence.
The owner explicitly requested stop, handoff, and rest. Only closeout was performed
after that request. Resume engineering only when the owner asks to continue.

## Current outcome

The public lab and four reviewed r5 installers are live. The owner tried the public
flow as an outside user, registered an account, downloaded and opened the Windows
Worker, and reported severe UX and functionality problems. Native Windows
acceptance is **blocked by reported problems**, not complete. No source patch or
new installer was produced after the feedback. Do not describe r5 as finished or
ready for ordinary users based on the CPU suite or download checks.

## Live state checked at close

- Repositories A `/home/pc5070ti/projects/hetero-es-m3-runtime` and B
  `/home/pc5070ti/projects/Hetero-ES-LLM-m3`: branch `feat/local-first-lf1`, no push/tag.
- Web/API/downloads: `https://lab.heteroes.site`; compute control:
  `https://compute.heteroes.site`; private compute `http://100.110.165.40:8769`.
- `heteroes-lab` user service active; tracked named tunnel, public entry and CPU
  backend alive. Public health HTTP 200, `ok: true`, `deviceConfiguration: true`.
- Manifest build `lf1-20261012-r5`; four public download links rendered and full
  public downloads matched the prepared sizes/SHA-256 hashes.
- Queue open; zero device/physical reservations and zero executing experiments.
  No GPU acceptance job was started. No owned diagnostic/test process remains.
- The live lab is intentionally left running. Manage it only with
  `scripts/local-lab.py`; do not kill its processes manually or change other
  owners' device preferences.

## What changed before this close

The unattended implementation checkpoint remains as recorded in the Codex handoff:
qualified Linux coordinator settings, read-only connection checks, conservative
pending configuration handling, admission hold/reconciliation split, agent command
negotiation, off-loop upload IO, and production single-writer locking.

When the owner asked how other people could install, the AI corrected its earlier
local-path guidance. It created and verified a private online SQLite snapshot,
managed-restarted the idle backend, and published the exact already reviewed r5
files using `--prepared-receipt`. No package was rebuilt and no new tunnel or
persistent system unit was configured. Evidence:
`evidence/2026-10-12-r5-public/`.

Local documentation commits recorded registration, download/navigation and
Worker-flow feedback. A convenience copy of the extracted Linux Worker and the
Windows installer is in `/home/pc5070ti/Downloads/HeteroES-r5-test/`; users should
normally download through the website. No default user app profile was enrolled
by the AI.

## User feedback and precise stopping point

All feedback is in `r5-user-feedback-2026-10-12.md`:

1. Twelve-character password minimum feels excessive; password input unpolished.
   No replacement password policy was decided or implemented.
2. Admin receives no obvious new-registration notification; approval screen ugly.
3. Registration goes straight to workspaces; homepage/download path is hard to
   discover. The user had to navigate GPU machines/devices to find the installer.
4. Worker login is mixed with network/role/check sections and is confusing.
5. Windows tray/in-app exit, sign-out and network/role controls appear unusable.
6. Final clarification: the user had not reached runtime installation/pairing and
   could not get through lab-address entry. Do not assume successful Worker login
   or an active runtime/GPU operation from their earlier description.

The two intended test machines are on **different networks**. The user chose
Windows first. Public cross-network compute is replay-only; LAN/overlay proof
would be a separate pass. Windows is Worker-only by design. Public routing to a
newly selected Linux coordinator is still manual and unfinished.

## Investigation done, with limits

Only read-only source inspection and isolated CPU/Linux r5 probes were performed.
The Xvfb probe reached the sign-in input after connecting to the public lab but
still returned `connection: OFFLINE`. Clicking Quit closed the page during the
Playwright click and the probe ended nonzero before its result JSON. These are
observations, not successful Windows reproduction or passing regression tests.
See `evidence/2026-10-12-worker-lifecycle/README.md`; retain its limitations.

Potential areas: silent tray error handling, main/renderer busy gates, connection
status after `Service.connect()`, and confusing progressive onboarding. Diagnose
the actual Windows state before changing shutdown semantics. Keep confirmed drain
for owned processes; do not solve usability by abandoning active work.

## Next work after the owner resumes

1. Start with fresh native Windows launch and lab connection, capture the exact
   visible error/state with the owner, and test every tray/in-app exit action.
   Do not repeat instructions that assume connection/sign-in succeeded.
2. Write a regression that fails for the reproduced fault, implement the bounded
   fix, run relevant tests and scratch mutation checks, then build a **new**
   immutable installer name. Never replace reviewed r5 bytes at their URLs.
3. Verify native Windows lifecycle and sign-out before asking for runtime/GPU tests.
   Improve onboarding: clear current step, visible download/home links, account
   approval status and accessible exit; then administrator notification/review UX.
4. Revisit password policy deliberately, consistently across backend, web and apps.
5. Resume GPU qualification and two-machine/public-route tests only after basic
   UX works and the owner authorizes the relevant machine/GPU work.

Larger identity/epoch, export/restore, graphical network/public-ingress setup and
remaining numerical acceptance backlog is unchanged. Do not start these while
the reported desktop blockers remain unresolved.

## Existing validation and recovery

Earlier CPU results, **not rerun during this user walkthrough**: runtime 2,115
passed/100 skipped; backend 221; Worker Node 25; Server Node 1; final selected
mutation faults 45/45 detected. Earlier clean Linux installation used isolated
profiles/Xvfb; it did not establish native Windows or ordinary desktop acceptance.

Original archives `~/.local/share/heteroes-session-archives/2026-10-12-lf1/` and
`2026-10-12-codex-r5/` are retained. Pre-public-update private snapshot:
`~/.local/share/heteroes-session-archives/r5-public-20261012T130611Z/`.
This close also produces a new archive at
`~/.local/share/heteroes-session-archives/2026-10-12-session-close/`, with exact
commit heads, verified Git bundles and a fresh online SQLite snapshot. Its receipt
records the encrypted Archive-2tb copy and restore checks. Read the receipt for
the final commit hashes; documents cannot embed the hash of their own commit.

Protected DB copies may contain password hashes, sessions and device grants.
Keep system archives private and Archive copies encrypted. Never print recovery
key/credential contents. These snapshots are not whole-lab restore exports.

First checks on an owner-authorized resume:

```bash
git status --short && git log --oneline -5
python3 -I scripts/local-lab.py status
systemctl --user is-active heteroes-lab
```

Keep the owner rules: Vietnamese short explanations; no push/tag/generated-by
trailers; tests then scratch mutation for new code; GPU gate and explicit machine
authorization; never `/mnt/sekai`; verify Archive UUID before writes; frozen
Recipe v1 numerical directories require a separate decision.
