# Workstation lab operations

The public lab is installed at `~/.local/share/heteroes-lab/app` at `10457f9a`. It uses its own
`~/.local/share/heteroes-lab/venv-backend` and combined SQLite/filesystem deployment. Caddy and Cloudflare expose the
CPU API/web and compute control when the lab is healthy. Private configuration lives at `~/.config/heteroes-m2`.

On 2026-11-21, the deployed status command reported all three services stopped. The user unit was in automatic
restart and its journal reported that the configured storage UUID was missing from the lab's storage path.
The installed unit already uses the venv Python. Check the intended mount and UUID before making the disk available.
The unit retries every 30 seconds. Once storage is available, use the status command to confirm recovery.

## Read-only checks

```bash
python3 -I "$HOME/.local/share/heteroes-lab/app/scripts/local-lab.py" status
systemctl --user show heteroes-lab.service -p ActiveState -p SubState -p Result
```

The status command checks the saved process ownership. After a restart, confirm the web/API service is reachable and
review dispatch hold before allowing new work.

## Operating the deployed clone

Use the deployed copy's `local-lab.py` for start/stop/restart/boot operations. It holds admission for maintenance, refuses
unsafe restarts with live work/reservations, and requires review before dispatching after an interrupted deployment.
A queue hold does not stop reconciliation of already admitted work. Device contribution is boot-scoped and starts OFF.

The systemd user unit supervises this deployed copy. The owner performs unit-level operations when needed.
Use the deployed clone for service operations and plan any source rollout separately. The last published installer line
is r10. [Release and rollback record](../RELEASE-NOTES-2026-10-28.md).

## Isolated development lab

Point the server at a separately initialized private directory, database and ports.

```bash
CUDA_VISIBLE_DEVICES='' .venv-backend/bin/python -m backend.server \
  --private /path/to/private-lab --web /path/to/built-web --headless
```

The factory requires explicit configuration and agent mode. Local recovery points publish a final verified
manifest. Use `scripts/restore-metadata.py` for SQLite metadata and `scripts/recovery.py` for generation recovery import
or restore. Restore into a fresh held deployment, retain unknown reservations and follow the owner/epoch limits in
[ADR-007](../../runtime/docs/adr/ADR-007-identities-versions-and-recovery.md).
For the source tree's split deployment, see [PostgreSQL restore](../design/postgres-metadata-backup.md).
See [HANDOFF.md](../HANDOFF.md), [server-desktop-guide.md](server-desktop-guide.md) and [SECURITY-NOTES.md](../SECURITY-NOTES.md).
