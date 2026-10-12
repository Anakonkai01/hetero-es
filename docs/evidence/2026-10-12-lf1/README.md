# Build lf1-20261012 — fresh-install checks of the new Linux apps

Built 2026-10-12 from branch `feat/local-first-lf1` (this repo) and the same-named
branch of the runtime repo. Build output (not in Git): 
`/mnt/Archive-2tb/heteroes-local/downloads/lf1-20261012/{server,worker}` with
`linux-unpacked` and the Windows `…Setup 0.1.0.exe` for each app.

| File | What it shows |
|---|---|
| `packaged-linux-server.json` | The packaged **Lab Server** (Linux) installed into an empty, isolated profile, bootstrapped a lab, served the Web UI and API on one origin, started with the queue held, stopped on request and restarted without losing the lab. Its `runtimeSha256` is the server runtime built for this build. |
| `packaged-linux-install.json` | The packaged **Worker** (Linux) installed its isolated runtime from the shared verified download cache, used a real GNOME libsecret keyring, and stayed unenrolled and OFF. `gpuWork` is false. |

Both runs used a virtual display (Xvfb), isolated `XDG_*` directories and the scripts
`scripts/check-linux-server.cjs` and `scripts/check-linux-packaged.cjs --phase install`.

## What this does NOT show

- No ordinary person walked through the apps on a normal desktop
  (`ordinaryOwnerDesktopWalkthrough` is false).
- Nothing about the **Windows** installers: they were built (Wine/NSIS) but not
  installed or run. They are unsigned.
- No GPU work, no pairing with a live lab, no job. Compatibility check (GPU) not run.
- The installers are not yet published to the running lab's download page.

## Hashes of the Windows installers built here

```
e69a4264e0e961c9d2ba8aff9f36c51f7d354873a01f3f639e0990a442dbe7c3  server/HeteroES Lab Server Setup 0.1.0.exe
492a2be4e6bb2142816645f91b3ebfe49eed8d65c57ac07eac515d8c6cd8d248  worker/HeteroES Worker Setup 0.1.0.exe
```
