# Build lf1-20261012 — evidence for the apps, the download page and the public route

Built 2026-10-12 from branch `feat/local-first-lf1` of this repository and of the runtime
repository. Build output (not in Git): `/mnt/Archive-2tb/heteroes-local/downloads/lf1-20261012-r3/`.
Earlier trial builds of the same day (`lf1-20261012`, `-r2`) are superseded by r3.

## 1. Fresh-install checks of the Linux apps (build r3)

| File | What it shows |
|---|---|
| `r3-packaged-linux-server.json` | The packaged **Lab Server** installed into an empty isolated profile, bootstrapped a lab, served Web and API on one origin, started with the queue held, stopped on request and restarted without losing the lab. |
| `r3-packaged-linux-install.json` | The packaged **Worker** installed its isolated runtime from the shared verified download cache, used a real GNOME libsecret keyring, and stayed unenrolled and OFF (`gpuWork` is false). |
| `packaged-linux-server.json`, `packaged-linux-install.json` | The same two checks for the earlier build r1. |

Both used Xvfb, isolated `XDG_*` directories and `scripts/check-linux-server.cjs` /
`scripts/check-linux-packaged.cjs --phase install`.

## 2. Published installers (receipt: `installers.json`)

| App | Platform | File | Bytes | SHA-256 |
|---|---|---|---|---|
| Worker | windows | `HeteroES Worker-0.1.0-lf1-20261012-r3-Windows.exe` | 102909693 | `2ab159dacfb46822b8d24af22190c1234e27855464b66335bb2cc5fbf5786d7e` |
| Worker | linux | `HeteroES Worker-0.1.0-lf1-20261012-r3-Linux.tar.gz` | 123810783 | `b9a29ca2e8ed2e42f7cd65113269e93597004b7151fc49b4171dde02d5d82888` |
| Lab Server | windows | `HeteroES Lab Server-0.1.0-lf1-20261012-r3-Windows.exe` | 103920193 | `cd24ec17a76e9aab88c87a631133f31b69730eea50a95dccb5436b502b6fa758` |
| Lab Server | linux | `HeteroES Lab Server-0.1.0-lf1-20261012-r3-Linux.tar.gz` | 124821212 | `a6dd8646bd3e8ec173f5c2f7edcb05ad075575ba84684bee4b808683f2504f84` |

The four files were published to the running lab's download page on 2026-10-12 and
downloaded in full through the public Quick Tunnel address; sizes and hashes were compared
with this receipt (see the work log of the session; result in section 4).

## 3. Real GPU run through the public address only (`public-replay.json`)

`scripts/check-public-replay.py` made the device's advertised private address one nothing
listens on, so the worker agent could not use the private route and fell back to the lab's
public compute address (Cloudflare Quick Tunnel, then the Caddy entry, then the coordinator).
An RTX 5070 Ti, Recipe v1, workload `arith16`, 4 generations x 4 candidates.

| Result | Value |
|---|---|
| Experiment | COMPLETED, 4 generations |
| Worker coordinator address | the public HTTPS address |
| `--no-bulk`, bulk URL | True, None |
| Candidates committed by the worker | 16 |
| Parent-weights changes in the run | 3 |
| Verified replays | 3 (1 step each) |
| Whole-weights downloads (`sync`) | 0 |
| Device address and contribution restored | True / True |

## What this does NOT show

- Only one device, which was both coordinator and worker: it did not exercise a second machine,
  a different ISP or a Windows worker. The public route was forced by address, not by distance.
- Nothing about a worker that falls too far behind: it would stop with `needs_private_route`
  (unit-tested, not run on a GPU).
- Windows installers were built (Wine/NSIS) and downloaded, but never installed or run.
  They are unsigned.
- No ordinary person walked through the apps on a normal desktop.
- The addresses are temporary Quick Tunnel names that change when the tunnel restarts.

## 4. Download check of the published files

Each published file was downloaded in full through the public address and its SHA-256 and size
compared with `installers.json`: see `download-check.txt`.
