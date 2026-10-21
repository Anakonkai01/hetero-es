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

## Rollback (if B, C or D fails)

1. `local-lab.py stop` (r11 copy).
2. In the live copy `git checkout --detach 79876cb`, restore `frontend/dist` (and `frontend/public/downloads` if C ran) from
   `live-app.tar.gz`.
3. Move the r11 database aside, rename `product-r10-before-r11-20261021.sqlite` back to `product.sqlite` and
   `metadata-backups-r10` back (or restore `product.sqlite` from the Archive snapshot after checking its sha256).
4. `local-lab.py start` (r10 copy); status; sign in. Device pairings of r10 come back with the database.
