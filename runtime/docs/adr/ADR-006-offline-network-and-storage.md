# ADR-006 — Offline lab, network and storage adapters

Status: **PROPOSED**, with the owner decision D3 (2026-10-12) recorded as DECIDED.
Offline acceptance is [PENDING]; the Quick Tunnel checks show transport behaviour,
not a general outage guarantee. Related: ADR-004, ADR-005, ADR-007.

Evidence labels: **[CODE]** exists in the inspected tree · **[MEASURED]** a dated
run in evidence · **[PROPOSED]** recommendation · **[PENDING]** not yet accepted
by a test or run.

## "Offline" is three different tests

| Condition | Contract | Evidence |
|---|---|---|
| No outbound Internet, LAN still works | A provisioned lab can log in, queue, train, pause/resume and restore | Parts exist [CODE]; the whole path is [PENDING] — **this is the MVP guarantee** |
| Optional hosted portal unreachable | Local lab is unaffected | Portal does not exist; keep it that way |
| Lab Server unreachable | Running work continues, control waits (ADR-005, D4) | [MEASURED] one 40.055 s outage; full matrix [PENDING] |

## Decision

1. **Offline means a pre-seeded, hash-verified cache.** **DECIDED (D3).** The
   installer already checks the SHA-256 of each file before downloading, and installs
   wheels with `pip --no-index --require-hashes`. [CODE] `desktop/worker/electron/
   download.cjs`, `setup.cjs`. So an offline install is: copy the cache folder (USB
   or disk), install. The only network actions today are the Python archive, the
   wheels and the model files.
   - Bundle size [CODE: from `profile.json`]: Linux worker ≈ 3.8 GB (Python 34 MB,
     53 wheels 2.76 GB, model files ≈ 1.0 GB); Windows ≈ 3.0 GB; the Lab Server
     profile is small (pure-Python wheels).
   - **Not in the bundle:** the NVIDIA driver. It must be preinstalled and compatible
     with the pinned `torch 2.13.0+cu132`. List it in the support matrix.
   - Add an `offline` setting that uses only the cache and fails with a clear error
     instead of trying the network; a missing or corrupt file is rejected, never
     fetched silently. [PROPOSED] ticket 2.1–2.2
   - A "LAN mirror" is **out of the MVP**: downloads require `https:` [CODE].
2. **Addresses are numeric private IPs; a fixed IP or a DHCP reservation is a
   documented prerequisite.** **DECIDED (D3).** [CODE] `addresses.py:21-23`,
   `server.py:32-34`: private and bulk endpoints reject host names, so a changed IP
   breaks the lab. `doctor` warns when the address looks dynamic. Host-name support
   is deferred.
3. **Plain HTTP on the LAN, with a warning.** **DECIDED (D3).** Session tokens,
   device tokens and compute grants travel unencrypted [CODE] (`http_transport.py`
   docstring). `doctor` says so. On a shared network (campus, dormitory) use an
   encrypted overlay (WireGuard, Tailscale, Headscale); the code already accepts
   `100.64.0.0/10`. TLS with a local certificate authority is deferred.
4. **Public routes.** A public control endpoint needs an HTTPS host name; large
   transfers (full weights, installers, backups, local-storage URLs) are denied on
   the public side and need a private route [CODE] `deployment.py`,
   `devices.py:106-110`. That rule exists because of Quick Tunnel limits. Keep it as
   the default, but make "this ingress can carry bulk" a declared capability of the
   ingress, not a law of the architecture. Replay shrinks traffic but a full-sync
   fallback still needs the bulk route.
   **Implemented and measured for one device (2026-10-12).** A worker with no private route
   runs *replay only* over the public address: its client refuses whole weights
   (`BulkUnavailableError`), it may follow up to 64 update records, and it stops with
   `needs_private_route` if it ever needs a download. The device agent probes the private route
   first and uses the lab's `publicComputeUrl` otherwise. [CODE] [MEASURED: one RTX 5070 Ti,
   4 generations, 3 verified replays, 0 downloads; a second machine and the stop path on a GPU
   are [PENDING]]. On the same network both replay and full download stay available.
   A fixed domain behind Cloudflare answers `403 error code: 1010` to urllib's default
   `Python-urllib` signature (a trycloudflare.com link does not), so every client sends its own
   `User-Agent` (`HeteroES-Worker/1`); [CODE] [MEASURED: the same run on `compute.heteroes.site`].
5. **Storage.** Local filesystem content-addressed storage is the default; an
   S3-compatible adapter is optional [CODE]. Objects are immutable by hash, a point is
   READY only after its final manifest, grants are scoped and short-lived. An upload
   or quota failure is recorded as "pending sync" and never fails a valid ES update
   [CODE] `cloud_sync.py`. For acceptance, at least one verified copy must be on a
   **different disk or host from the coordinator** [PROPOSED]. Live SQLite, runtimes
   and credentials stay on the local disk.
6. **Provider code stays behind adapters.** Numerical code never imports AWS/R2;
   labels such as `CloudStorage`/`cloudSync` are legacy names and may be renamed only
   with compatibility aliases.
7. **The apps offer three network choices and a connection check. DECIDED 2026-10-12
   (D8); implementation [PROPOSED], tickets E2.**
   - *Same LAN* — the app lists the computer's private addresses (the Lab Server app
     already does, `desktop/server/electron/service.cjs`).
   - *Tailscale / WireGuard overlay* — recommended when machines are on different
     networks. It behaves like a LAN, so every LAN rule above applies unchanged. The
     Worker guide already asks for Tailscale first.
   - *Internet over HTTPS* — advanced; needs a host name and a private bulk route
     (decision 4). Deferred.

   **"Check connection"** runs from the Worker side and reports PASS/FAIL for each
   step: reach the Lab Server (control); reach the coordinator (control, with the
   device credential); fetch a short byte range of a large file (bulk). It extends the
   `doctor` command (ticket 1.6) so one tool answers "why can't this machine join?".
   Today changing the Lab Server address means stopping it and editing its private
   configuration; a graphical flow for that is [PENDING] and deferred.

## Known defects to fix before shipping this path

- Local-storage upload is an `async` route doing blocking writes, `fsync` and hashing
  on the event loop; it can stall agent polls during a large upload. [CODE]
  `local_storage.py:172-201` (ticket 1.5)
- A personal-machine rule (`/mnt/sekai` forbidden) is hard-coded in shipped code;
  move it to configuration. [CODE] `local_storage.py:40-41`
- `cloud_sync.upload` reads a whole object into memory (up to 5 GB) beside the
  training process. [CODE] `cloud_sync.py:27-28` (low priority)

## Acceptance

From an empty cache, with outbound DNS and routes blocked: install the Lab Server and
a worker/coordinator from the bundle, enroll, approve, turn ON, run a Recipe v1 job,
pause/resume with the baseline hash, read artifacts, restore onto a fresh path.
A damaged bundle file is rejected. Repeat on Windows only for the worker profile.
[PENDING — ticket 2.3]

## Still open

Which non-Tailscale bulk route to qualify first. It does not block a LAN-only lab.

## 2026-10-12 continuation — Worker connection checks

[CODE] The Worker app offers LAN, overlay and HTTPS choices. These choose the
coordinator's bind/advertised private address and describe the network; actual
worker routing still probes private control first, then public replay-only.
It does not install or configure a network adapter or tunnel.

[CODE] Read-only diagnostics check Lab Server health without resetting the login,
then use the Python bridge's assignment-scoped compute grant for coordinator
health. A private route fetches `bytes=0-63` of the current published weights;
HTTP transport now supports bounded ranges as well as resumable open-ended
ranges. Public fallback never requests weights. No assignment or unpublished
weights is SKIP, not PASS. Redirects cannot forward the compute grant.

[MEASURED — CPU fixtures only] Real loopback HTTP and Electron checks, including
wrong credentials and actual wire byte counts, are in product
`docs/evidence/2026-10-12-lf1-codex/`. This is not a cross-network/GPU acceptance.
The Lab Server graphical network-choice flow and an extended CLI doctor remain
[PENDING].

## 2026-10-12 continuation — responsive local upload IO

[CODE] Local upload opening/preflight, bounded chunk writes/hash, fsync/publication
and cleanup run in the API thread pool. Cleanup serializes with any disk operation
still running after request cancellation. Signed length, immutability and
manifest-last publication rules remain in force.

[MEASURED — CPU fixtures] An unrelated async health request succeeds while a
synthetically slow open/write/fsync is waiting. Incomplete/oversized/disconnected
uploads clean up their partial file; cancellation does not close a descriptor still
owned by the disk thread. Six mutation faults are detected. This is responsiveness
under controlled disk delay, not a large-object throughput or crash/power-loss test.

[MEASURED] Both r5 Linux desktop installers passed with private profiles on the
system filesystem. The first Server profile was mistakenly put on this machine's
Archive mount (directory mode 0777) and was refused. Private state/runtimes remain
on the system filesystem; Archive is for selected bulk data. See product evidence
`docs/evidence/2026-10-12-lf1-codex/` and `docs/r5-hardware-acceptance.md`.
