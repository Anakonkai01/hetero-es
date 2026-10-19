# Workstation lab operations

The live lab runs from `~/.local/share/heteroes-lab/app`, a deployed clone at `79876cb`, with its separate environment
`~/.local/share/heteroes-lab/venv-backend`. Caddy and Cloudflare ingress expose the local CPU API/web and compute control.
Private configuration is in `~/.config/heteroes-m2`; do not print it or copy it into evidence.

```bash
python3 -I "$HOME/.local/share/heteroes-lab/app/scripts/local-lab.py" status
```

Use the deployed copy's `local-lab.py` for start/stop/restart/boot operations. It holds admission for maintenance, refuses
unsafe restarts with live work/reservations, and requires review before dispatching after an interrupted deployment.
A queue hold does not stop reconciliation of already admitted work. Device contribution is boot-scoped and starts OFF.

The systemd user unit supervises this deployed copy. Do not invoke a unit restart or kill its processes manually from an
agent session. The owner performs unit-level operations when needed. The cleanup did not change the deployed clone,
private configuration, device choices or published r10 installers. Moving local `main` is not deployment.

For a separate initialized development lab, use its own private directory/database/ports:

```bash
CUDA_VISIBLE_DEVICES='' .venv-backend/bin/python -m backend.server \
  --private /path/to/private-lab --web /path/to/built-web --headless
```

The factory requires explicit configuration and agent mode. Local recovery points publish a final verified manifest;
metadata backup/restore uses `scripts/restore-metadata.py`, and generation recovery import/restore uses `scripts/recovery.py`.
Restore into a fresh held deployment, retain unknown reservations and follow the owner/epoch limitations in ADR-007.
See [HANDOFF.md](HANDOFF.md), [server-desktop-guide.md](server-desktop-guide.md) and [SECURITY-NOTES.md](SECURITY-NOTES.md).
