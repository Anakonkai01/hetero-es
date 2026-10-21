# r11 flag day (2026-10-21, owner present)

`plan-r11-release.md` step 7. Release commit `93ff85f28651988a484be69383f0e78cc6c78d0d` (origin `main`), build
`lf1-20261021-r11-candidate9`. Each irreversible action waits for the owner's "đồng ý" in chat.

## 7.1 Read-only status (19:48 +07)

`local-lab.py status` (live copy at `79876cb`): named tunnel, public entry and CPU server alive; `https://lab.heteroes.site`.
Live database, read-only: 4 users, 2 workspaces, 26 experiments (17 COMPLETED, 7 CANCELLED, 2 FAILED, none running),
0 unreleased assignments, empty queue, 0 device or physical reservations. 6 device rows: `5070ti` APPROVED (last seen 10-13),
four REVOKED, and one `3060-thao` (`desktop-a3a6275dfe33`) APPROVED but last seen 10-14 (the original r10 Windows Worker whose
data backup the owner deleted today). Nothing is running, so the switch does not interrupt work.

## 7.2 Backup (19:49 +07), verified

`flagday-backup.py` wrote a new folder `/mnt/Archive-2tb/heteroes-local/backups/r11-flag-day-20261021/` (Archive UUID
`10443D1F443D094C` checked; mode 0700/0600; it holds private secrets and is never copied into the repo):

| file | what | sha256 (first 16) |
| ---- | ---- | ----------------- |
| `product.sqlite` | consistent snapshot of the live database (SQLite backup API, source read-only) | `32bf4d49ad110aa2` |
| `live-app.tar.gz` | the deployed copy at `79876cb` including its built `frontend/dist` and published downloads | `7b52442db48801ba` |
| `venv-backend.tar.gz` | the live backend environment | `1c55b26da1df7001` |
| `private-config.tar.gz` | `~/.config/heteroes-m2` without the live database file (config, credentials, signing key, tunnel config, hourly metadata backups) | `f6a3b4dd208afbc9` |
| `systemd-unit.tar.gz` | `heteroes-lab.service` | `7230e036000bf991` |

`flagday-verify.py`: all hashes equal `backup.json`; every archive lists (7435, 6505, 261, 1 members); database
`integrity_check` ok; row counts equal the live database (users, workspaces, experiments, devices, assignments, memberships);
the live copy's own `scripts/restore-m2-metadata.py` restores the snapshot into a scratch folder without error.
The lab's hourly metadata backups keep only 24 points, which is why this copy lives on the Archive disk.

## Switch procedure (to be confirmed step by step)

- **A (wipe):** `local-lab.py stop` from the live copy; rename `state/product.sqlite` to
  `state/product-r10-before-r11-20261021.sqlite` and `state/metadata-backups` to `state/metadata-backups-r10`. The r11
  server then creates a fresh database with only the `admin` account of `credentials.json` (unchanged): every other
  account, experiment, device and pairing of r10 is gone from the live lab (kept in the backup).
- **B (deploy):** in the live copy `git fetch origin && git checkout --detach 93ff85f`; replace `frontend/dist` with the
  candidate9 web build `/mnt/Archive-2tb/heteroes-local/downloads/lf1-20261021-r11-candidate9/web/` (built from the same
  frontend source; `index.html` sha256 `1bba6f29f29d8df9…`); backend requirements are unchanged between `79876cb` and
  `93ff85f`, so `venv-backend` stays; `local-lab.py start` (r11 copy) with the venv Python; status, sign-in, page check.
- **C (publish):** `scripts/publish-local-installers.py --prepared-receipt
  docs/evidence/2026-10-21-r11-candidate9/installers-prepared.json --receipt <this folder>/installers-published.json`.
  The candidate9 installers already default to `https://lab.heteroes.site`.
- **D (devices):** fresh candidate9 Worker on the 5070 Ti desktop and on Thao's Windows, pair, approve (never a revoked
  identity), self-tests; a 2-generation managed parity run with audits, verified as in candidate9.

## A done (owner "đồng ý", 19:53 +07)

`local-lab.py stop` (live copy `79876cb`): "Owned CPU service and tunnels stopped"; status: all three services not alive.
No `-wal`/`-shm` file left (the database was closed cleanly). Renamed `state/product.sqlite` →
`state/product-r10-before-r11-20261021.sqlite` (sha256 `5dd4d05150579d5e…`; written at the stop, 4 minutes after the
Archive snapshot, so it is the newer copy for a rollback) and `state/metadata-backups` → `state/metadata-backups-r10`.
lab.heteroes.site is offline until B. The isolated c9 lab (separate folder and ports) is not touched.

The owner chose to set the `admin` password themselves: the r11 server seeds `credentials.json` users only into an empty
database (`backend/store.py`), so the owner writes it before B in their own terminal (the AI never sees it).

## B done (owner "đồng ý B", 19:55-19:59 +07)

- The owner asked the AI to set the `admin` password (a simple one, by the owner's explicit choice: the lab is only switched
  on for work or demos). It was written into `credentials.json` before the start and replaced by `{"users": {}}` after the
  first sign-in, so no password stays in a file; the database keeps only the Argon2 hash.
- Live copy: `git fetch origin && git checkout --detach 93ff85f`; working tree clean; the release tracks nothing under
  `frontend/dist` or `frontend/public`, so the published downloads stayed. `frontend/dist` → `frontend/dist-r10`; the
  candidate9 web build copied in (`diff -r` equal; `index.html` sha256 `1bba6f29f29d8df9…`). The r11 backend imports in the
  unchanged `venv-backend`.
- **Deviation:** the first `local-lab.py start` stopped with `OperationalError` before any service started: r11's
  `local-lab.py` reads the product database (dispatch hold, reservations) before starting, and after A there was none. Fixed
  without code change: one call of the production `backend.app.app_from_environment()` (no serving; threads start only in the
  lifespan) created the schema, seeded `admin` (`platformAdmin`, `canCreateWorkspace` by migration), user_version 1,
  `dispatchHold` false, one default workspace. Then `local-lab.py start --python venv-backend/bin/python`: named tunnel,
  public entry and CPU server alive; "queue reopens when this action ends". (Product note for later: `local-lab.py` should
  initialize or explain a missing database.)
- Public checks: `https://lab.heteroes.site/` 200 (title HeteroES); `https://compute.heteroes.site/` 403 for a bare request
  (expected, it serves workers); sign-in as `admin` through the public URL 200, session 200, devices list 200 with 0 devices,
  sign-out 204. `/experiments` without a workspace header is 403 (scoped route), as designed.
- The systemd unit is unchanged; it runs the same `scripts/local-lab.py boot` path, now the r11 one.

## C done (owner "đồng ý C", 19:59 +07)

`publish-local-installers.py` (r11 live copy) with `--prepared-receipt ../2026-10-21-r11-candidate9/installers-prepared.json`
and the candidate9 package folder on the Archive: every file checked against the reviewed hashes before any link;
output `{"downloads": 4, "cloudPublish": false, "publiclyPublished": true}`; receipt `installers-published.json`. The r10
manifest was replaced (the r10 installer files and their links stay on disk).
`verify-public-lab.py --base https://lab.heteroes.site` (`public-verification.json`): the four installers downloaded through the
public URL with equal size and SHA-256, web pages 200, `allOk: true`, build `lf1-20261021-r11-candidate9`. The one-line Linux
installer `/downloads/install-worker.sh` points at `https://lab.heteroes.site/downloads`; its CLI bundle is served (200,
563038 bytes = the Archive file).

## Rollback (if B, C or D fails)

1. `local-lab.py stop` (r11 copy).
2. In the live copy `git checkout --detach 79876cb`, restore `frontend/dist` (and `frontend/public/downloads` if C ran) from
   `live-app.tar.gz`.
3. Move the r11 database aside, rename `product-r10-before-r11-20261021.sqlite` back to `product.sqlite` and
   `metadata-backups-r10` back (or restore `product.sqlite` from the Archive snapshot after checking its sha256).
4. `local-lab.py start` (r10 copy); status; sign in. Device pairings of r10 come back with the database.

## D started by the AI, then handed to the owner (20:05-20:15 +07)

The AI began D (downloaded the public one-line installer, equal to the prepared one, sha256 `9e2837c90cff…`; started a
coordinator CLI install on the 5070; installed the Worker on Thao's Windows from the public URL, hash equal to the receipt,
exit 0, `defaults.json` = `https://lab.heteroes.site`, `windows-install-live.log`). The owner then asked to do D themselves as
the final user acceptance (the coordinator runs on the 5070 Ti). The AI stopped both tasks and undid them:
`windows-undo-live.ps1` quit the app (4 processes), ran the candidate9 **silent uninstaller: exit 0, app, `%APPDATA%\@heteroes`
and data folder all gone**, removed the task folder (it held the admin login); the partial coordinator home on the 5070
(489 MB, no process left) was deleted. The live lab still has 0 devices and 0 pairing codes. No device was paired or approved.

## Public compute route port fixed (owner "đồng ý", 20:57 +07)

Owner test: Tailscale disconnected on Thao's Windows (its WSL keeps its own tailnet address, which Windows does not use):
from Windows, `100.110.165.40` ports 8002/8765/8769 unreachable; `https://compute.heteroes.site/v1/health` → 502.
**Found:** every coordinator (desktop `service.cjs:407`, CLI `worker_cli.py:253`, `agent.py:147`) listens on port **8765**, but
the lab's `privateComputeUrl` (r10 leftover) was `http://100.110.165.40:8769`, so the public tunnel forwarded worker traffic to a
port where nothing listens. Fixed without code change: `local-lab.py restart --compute-url http://100.110.165.40:8765`
(lab idle); `config.json` now holds 8765 and the generated Caddyfile forwards the compute host's protocol paths to it; three
services alive, web 200. The route answers only while a coordinator runs on the 5070 (502 before that, as expected).
Limits (backlog): one public compute route per lab, to one port on the lab machine (a coordinator elsewhere needs a private
network); the default/installer configuration should not let `privateComputeUrl` and the coordinator port drift apart.

## D by the owner, with AI help on the CLI machines (20:20-21:15 +07)

- Thao Windows (owner): Worker from the public download, data folder `F:\HeteroES-Worker-data` (fresh downloads 1.85 GB +
  model 0.93 GB, app log `install ok ms=134905`), paired as `3060-thao` (new identity `desktop-d9017660e75f`), approved, ON.
- 5070 Ti (owner): the Linux desktop tarball failed to start (owner's report; message to be recorded), so the CLI was used.
  The first `curl … | bash` stopped twice on `urlopen error … handshake operation timed out` (the CLI downloader has no retry
  and no progress for large files); a retry loop finished it. First pairing without `--coordinator` (`host 127.0.0.1`), so it
  was revoked and re-paired as `5070ti-nhan` with `--coordinator --host 100.110.165.40` (no rename and no "forget" in the CLI).
- 1660S and Quang (AI, owner's request): `reinstall-cli.sh` stopped the old isolated-lab agent, removed the old install and
  pairing but kept the verified downloads, reinstalled from the public installer, GPU self-test PASS (GTX 1660 SUPER,
  RTX 3060 with `LD_LIBRARY_PATH=/usr/lib/wsl/lib`); paired with one-time codes from `pairing-code.py` piped into `join`
  (Quang's first `join` failed with "Remote end closed connection without response", the second worked); agents started with
  `nohup setsid … run`, ONLINE, waiting for approval.
