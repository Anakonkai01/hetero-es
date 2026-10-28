# Lab release deploy, 2026-10-28

The deployed clone `~/.local/share/heteroes-lab/app` moved from `82c37fca` to `main` = `10457f9a` (accepted source tree
`src-18d0b138`, see `docs/acceptance/STATUS.md` on main), its web UI was rebuilt into `frontend/dist` (the previous build
is kept outside the repository for rollback), the researcher notebook and SDK wheel in `frontend/dist/notebooks` were
replaced by this commit's, and the lab was started with `scripts/local-lab.py start` (backend venv Python).

`verify-public-lab.json`: `scripts/verify-public-lab.py --base https://lab.heteroes.site` without credentials:
`allOk: true` (health, web pages, every published installer's size and SHA-256). The served `index.html` names the new
bundle `assets/index-AYtRbE0n.js`; the served SDK wheel has the same SHA-256 as the built one.

Found while deploying: the systemd user unit had been failing since 2026-10-23 10:26 (768 restarts): it runs
`local-lab.py` with `/usr/bin/python3 -I`, and since `8c66ca52` (2026-10-19) `local-lab.py` imports `backend.deployment`
-> `backend.policies` -> `fastapi`, which that interpreter does not have. The lab was therefore down from that reboot on.

## What this does NOT show

- The signed-in part of verify-public-lab.py did not run (the credentials file has no `admin` entry); no run timeline or
  event stream was read.
- No worker joined and no run was started after the deploy; device states were not changed.
- The systemd unit is not fixed by this deploy; a reboot brings the lab down again until its ExecStart uses the venv Python.
