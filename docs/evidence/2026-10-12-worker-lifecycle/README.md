# Unfinished Worker lifecycle investigation — 2026-10-12

The owner reported confusing and unusable Windows onboarding, tray/in-app exit,
sign-out, and network/role controls. Their final clarification places the failure
before runtime installation/pairing, at lab-address connection. No source patch,
new installer or passing regression test was produced before they requested stop.

Two CPU-only probes used the already published r5 Linux unpacked app, with fresh
isolated system-disk XDG profiles. No login credentials, enrollment or GPU were
used. The first launch lacked DISPLAY and failed to initialize X11; this is a
probe environment failure, not evidence of the Windows fault.

The second probe used Xvfb and Playwright's launch arguments. An IPC status call
succeeded with compute settings present and no paired device. Filling the public
lab URL and submitting reached the username input without renderer page errors.
A subsequent status still reported `connection: OFFLINE`. Source inspection shows
`Service.connect()` does not update `this.connection` after successful health
validation, unlike `Service.api()`. This is a candidate status-display defect,
not an established explanation of the Windows failures.

`r5-before-quit.png` is the isolated Linux screen before pressing Quit safely.
The click closed the page during Playwright's click call, which raised
`Target page, context or browser has been closed`. The probe exited nonzero before
writing its planned result JSON. This is not a passing exit test; the next agent
should explicitly await the app close event and handle the expected page-close
race. Final process inspection found no owned diagnostic Node/Electron process,
and the temporary XDG profiles were removed.

Source observations to investigate, without claiming a Windows root cause:

- Main IPC rejects other actions while `busy`; tray errors only call `show()`.
- Renderer disables exit, sign-out and network controls while an action is busy.
- `Service.quit()` rejects while runtime setup or qualification is running.
- A window close hides to tray by design; it is distinct from a Quit action.
- Windows is intentionally Worker-only; coordinator eligibility is Linux-specific.

## What this does NOT show

This does not reproduce the user's Windows failure or establish its root cause.
It does not prove successful Windows connection/login/exit, Linux native desktop
acceptance, GPU compatibility, safe drain under work, or two-machine acceptance.
No automated mutation/regression check was run for this unfinished investigation.
