# r5: real desktop and two-machine acceptance

Build: `lf1-20261012-r5`. Four installers and verified hashes are listed in
`evidence/2026-10-12-lf1-codex/installers-r5-prepared.json`. They are prepared on
Archive-2tb and published at `https://lab.heteroes.site/#downloads` on 2026-10-12.
The live backend was updated through its managed idle restart. Public full-download
hash verification is recorded in `evidence/2026-10-12-r5-public/`.
Windows installers are unsigned. Do not treat a successful build as Windows acceptance.

## Which lab to use

For the coordinator toggle and role changes, use the updated public lab or the
new r5 Lab Server in a fresh test lab. Other labs still running r4 need a managed
backend update first. A fresh lab starts with admission held.

Use a normal system profile for the apps. On Linux keep private configuration,
SQLite and Python runtimes on the system filesystem; the Archive disk in this
workstation's current mount exposes directories as 0777 and is unsuitable for
private Lab Server state. Bulk model/artifact storage may use the chosen data disk.

## First pass: one Windows and one Linux desktop

| Check | Expected result |
|---|---|
| Launch the installer/app normally, without the automation harness | App opens on the real desktop; no terminal workaround needed |
| Install isolated runtime | Completes with the verified cache/downloads; a clear error on failure |
| Connect, sign in and run compatibility | Passed numerical compatibility; GPU name and physical identity shown |
| Windows role selection | Worker only; no coordinator checkbox |
| Linux role selection after qualification | Coordinator checkbox only when capability is reported and VRAM is at least 11000 MB |
| Pair, approve, reopen the app | Same device identity retained; contribution starts OFF |
| Turn ON, Stop safely, Quit safely | Owner explicitly enables; stop/drain is confirmed before exit |
| Close the window and reopen from tray | App stays alive in tray and can be reopened |

If compatibility fails, keep contribution OFF and export diagnostics. Do not
approve an incompatible device merely to finish the checklist.

## Second pass: a small two-machine Recipe v1 job

1. Pick a fixed LAN/overlay IPv4 address in the Linux coordinator app. Every worker
   must be able to reach that address. Selecting it does not install Tailscale,
   WireGuard, a firewall rule or a tunnel.
2. Pair and approve both devices in the test lab. Enable contribution deliberately.
   Open admission when ready.
3. Submit an `arith16` Recipe v1 job with four generations and four candidates.
   Record which physical machine coordinates and which workers participate.
4. Run connection checks while a worker assignment exists. Expect Lab Server and
   coordinator PASS. Private weights probe passes only once weights are published;
   no assignment/unpublished weights is explicitly untested.
5. Hold admission during the run: its status continues to update, a second job
   waits, and cancel/pause still reaches the current assignment.
6. Stop safely. Check that reservations remain until all owned processes are
   confirmed stopped. Never free a reservation just because a device is offline.

The public HTTPS replay-only test is a separate pass: its compute ingress must
point to the chosen coordinator. Automatic public ingress wiring for a new
coordinator is still missing. Use the existing controlled acceptance script or an
operator-configured route; do not claim another-network acceptance from a LAN test.

## What to retain

Build/OS/driver/GPU names, the route used, screenshots of compatibility and
connection results, a diagnostics export, and the experiment's result/status.
Keep passwords, device credentials, signed URLs and raw private configuration out
of shared screenshots/reports. Add evidence under a fresh dated folder with
"What this does NOT show". Prior CPU/Xvfb evidence is not the native-desktop result.

For agent-operated GPU scripts the original owner gate still applies:
explicit `--gpu` plus `HETEROES_GPU_ACCEPTANCE=1`, and owner authorization. A second
machine or SSH test also needs the owner first.
