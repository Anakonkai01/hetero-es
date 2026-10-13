# r6 — first-minutes fixes (2026-10-13)

Answers the owner's r5 walkthrough feedback (`docs/r5-user-feedback-2026-10-12.md`). Build **lf1-20261013-r6**
is **prepared, not published**: `installers-r6.json` has `"publiclyPublished": false` and the live download page still
serves r5. The r5 files and links were not touched.

## What changed (all on branch `feat/local-first-lf1`, nothing pushed)

| Reported problem | Cause found in the source | Change |
| --- | --- | --- |
| Could not get through the lab address | The field was `type="url"` (browser refuses `lab.heteroes.site`), the placeholder was a private Tailscale address, a raw `TypeError` became the generic `ACTION_FAILED` | Address is accepted as typed or pasted (`lab.heteroes.site`, `https://lab.heteroes.site/#downloads`; only the origin is kept), is pre-filled from `resources/defaults.json`, and every failure has a code and a sentence (`INVALID_LAB_ADDRESS`, `LAB_UNREACHABLE`, `LAB_TIMEOUT`, `NOT_A_LAB`, `LAB_HTTP_5xx`, …) |
| App said OFFLINE after connecting | `Service.connect()` never set the connection state | Sets ONLINE on success; a failed attempt at another address does not flip a working connection |
| Quit / tray only reopened the window | Tray handlers ended in `.catch(() => show())`; Quit was refused while another action (a hanging connect, up to 15 s) held the gate; the footer Quit button was disabled while busy | `Lifecycle` (new, testable): Quit is never refused, cancels waiting reads and sign-in (never pairing), coalesces repeated clicks; every tray/startup failure shows a message with its code |
| Could not sign out / back in | `logout()` set `autoStart=false` and nothing reset it, so after signing in again the agent never restarted | Sign-in re-enables the agent (contribution still OFF) |
| Startup failures were invisible | `whenReady().catch(() => app.quit())` | Logged to `worker.log` (no secrets), shown in a message box; the log tail is part of "Export diagnostics" |
| Confusing Worker screen | Network/role/diagnostics shown beside the sign-in step | They are collapsed while onboarding; the step is first; "Change lab" is available at sign-in; footer shows the build name |
| 12-character password | `backend/lab.py` | Minimum 8, refuses common/blank/own-name passwords, plain-sentence errors (`backend/passwords.py`); the initial Lab Server administrator keeps its own stricter rule |
| Could not find the download after registering | Registration went straight to `/workspace` | Registration lands on **Get started** (status, download buttons, lab address, pairing steps); **Home** and **Get started** are in the navigation |
| Admin not told about new registrations / ugly approval screen | Nothing polled pending accounts | Badge on **Operations**, a banner on every page, pending requests first with Approve/Reject, a confirmation line; the other account actions sit under "All accounts" |

Operational fix found on the way: after a reboot this morning the lab did not start because `/mnt/Archive-2tb` was
not mounted (no `/etc/fstab` entry). `local-lab.py` now checks the pinned storage disk before it stops or starts
anything and says so; the user unit retries every 30 s. The disk itself still has to be mounted (see the handoff).

## Evidence

- `worker-packaged-linux/worker-onboarding.json` — `scripts/check-worker-onboarding.cjs --packaged` against the built
  **Linux r6 app** (real Electron, isolated profile, CPU fixture lab): default address, invalid/unreachable messages,
  ONLINE after connect, pasted URL reduced to its origin, change-lab, sign-out and back in, Quit while a connection
  hangs (exit in ~50 ms), plain Quit, `worker.log` without the password or session.
- `web-fixture-lab/` — `scripts/check-web-onboarding.mjs` against `scripts/serve-test-lab.py` (temporary state, Chromium):
  short and common passwords explained, show/hide, registration lands on Get started with working download links,
  administrator badge/banner, approval, banner clears, no horizontal overflow at 375/768/1280 px; two screenshots.
- Tests: backend 239 passed (221 + registration rules 15 + storage check 3); Worker Node 49 (was 25); Server Node 1;
  product-ui 2. Runtime (Track A) was not touched and not rerun.
- Mutation checks on scratch copies: Worker code 29/29 killed; password rules 13/13; storage check 4/5 (the survivor is
  equivalent: `findmnt` prints nothing on failure, so the `returncode` guard cannot change the result).
  One real gap was found and fixed by this process: an all-blank 8-character password was accepted.

## What this does NOT show

- **No Windows run.** Windows was not available. The Windows installer was built through Wine and its hash matches the
  receipt; the Electron code is the same as the Linux code that was driven, but tray behaviour, NSIS, SmartScreen,
  `safeStorage` and Windows networking are untested. Running the r5 Windows app under Wine only showed it exiting
  by itself a few seconds after start with no error output; that is not a reproduction of the reported fault.
- The exact cause of the owner's Windows failures is **not established**. The defects above were found by reading the
  source and are real (each has a failing-then-passing test), and they match the reported symptoms, but whether they
  are the whole story needs the owner's Windows run (the app now writes `worker.log`; the red box already shows an error code).
- Nothing here was applied to the **live lab**: the backend password rule, the web changes and the r6 installers still
  need a managed restart and publication (owner's go).
- No GPU work, no runtime install, no pairing with a real lab, no two-machine run.

## Addendum — published and live (2026-10-13, ~12:10, owner said "đưa luôn lên web")

The state above ("prepared, not published") was true when written. Afterwards, on the owner's go: the web build and the
8-character password rule were put live (`systemctl --user restart heteroes-lab`, queue idle and reopened), and r6 was
published with `--prepared-receipt` (`installers-r6-published.json`; r5 files and links remain). All four installers were
downloaded in full over `https://lab.heteroes.site` and match their SHA-256 and size (`public-download-verify.json`).
The live registration endpoint rejects a 7-character and a common password with the new sentences (no account was created to test acceptance;
that is covered by the backend tests). The Windows run is still the owner's.
Also fixed: the web build copied `public/downloads` (installer links, ~3 GB) into every build; `publicDir` is now `frontend/static`.
`/etc/fstab` still has no line for the Archive disk (only linger was enabled).
