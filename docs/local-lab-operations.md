# Running the lab on a workstation: start, stop, reboot

The lab is three processes managed by `scripts/local-lab.py`: the CPU Web/API (`backend.server`), the
public entry (Caddy, loopback ports 8080/8081) and the Cloudflare tunnel. Private configuration lives in
`~/.config/heteroes-m2/` (`config.json`, `credentials.json`, `local-deployment/`).

| Command | What it does |
|---|---|
| `python3 scripts/local-lab.py status` | Which of the three are alive, and the public names. Changes nothing. |
| `python3 -m backend.doctor --private ~/.config/heteroes-m2` | Read-only checklist (address, database, storage, public names). |
| `local-lab.py restart --python <backend venv python>` | Restarts the Web/API and the entry. **Holds the queue for the length of the restart and reopens it afterwards** if the lab was open and idle; refuses if a run or a GPU reservation is live. |
| `local-lab.py stop` / `start` | Stops or starts all three (same hold handling). |
| `local-lab.py boot` | Starts whatever is not running and never launches a job. If a run or reservation was live when the machine went down, the queue **stays held** until an administrator confirms in Operations. |

## Surviving a reboot

`deploy/heteroes-lab.user.service` is a systemd **user** unit that runs `boot` at login and a graceful `stop`
at shutdown. Install and enable it:

```bash
mkdir -p ~/.config/systemd/user && cp deploy/heteroes-lab.user.service ~/.config/systemd/user/heteroes-lab.service
systemctl --user daemon-reload && systemctl --user enable --now heteroes-lab
```

A user unit starts when the user's systemd instance starts. To have the lab come up after a reboot **before
anyone logs in**, run once with administrator rights: `sudo loginctl enable-linger $USER`.

Measured 2026-10-12 on this workstation: `systemctl --user stop heteroes-lab` then `start` gave a cold boot in
about one second; the public Web answered 200 within a few seconds once the tunnel had registered. A real
power cycle has not been tried.

## Fixed public names

The tunnel is `heteroes-lab-local` (configuration `local-deployment/named-config.yml`, credentials in
`~/.cloudflared/`). `lab.heteroes.site` serves the Web/API and installers; `compute.heteroes.site` serves only the
coordinator's control routes (never weights). Cloudflare's Browser Integrity Check rejects Python's default
User-Agent on these names, so every HeteroES client sends its own.
