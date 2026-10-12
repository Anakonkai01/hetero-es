# Build lf1-20261012 — evidence for the apps, the download page and the public route

Built and tested on 2026-10-12 from branch `feat/local-first-lf1` of this repository and of the
runtime repository. The current published build is **r4**; builds r1 to r3 of the same day are
superseded. Build output (not in Git): `/mnt/Archive-2tb/heteroes-local/downloads/lf1-20261012-r4/`.

## 1. Fresh-install checks of the Linux apps

| File | What it shows |
|---|---|
| `r4-packaged-linux-server.json` | The packaged **Lab Server** installed into an empty isolated profile, bootstrapped a lab, served Web and API on one origin, started with the queue held, stopped on request and restarted without losing the lab. |
| `r4-packaged-linux-install.json` | The packaged **Worker** installed its isolated runtime from the shared verified download cache, used a real GNOME libsecret keyring, and stayed unenrolled and OFF (`gpuWork` is false). |

The same two checks also passed for builds r1 and r3 (files without the `r4-` prefix and `r3-`).
They used Xvfb, isolated `XDG_*` directories and `scripts/check-linux-server.cjs` /
`scripts/check-linux-packaged.cjs --phase install`.

## 2. Published installers (receipt: `installers-r4.json`)

| App | Platform | File | Bytes | SHA-256 |
|---|---|---|---|---|
| Worker | windows | `HeteroES Worker-0.1.0-lf1-20261012-r4-Windows.exe` | 102910011 | `c26a7db340bc92df79c2a8b8e14304441031d5b12daf65daf6b056ba2a3e7f44` |
| Worker | linux | `HeteroES Worker-0.1.0-lf1-20261012-r4-Linux.tar.gz` | 123811040 | `701a177a8f9daff5160029036498413a02c0dca8075b547a19ef49f6fdf4bf44` |
| Lab Server | windows | `HeteroES Lab Server-0.1.0-lf1-20261012-r4-Windows.exe` | 103921747 | `d60fb9bc4403effb21737e73d573f0845c135db2bcccbd62a95b7becbae67cd6` |
| Lab Server | linux | `HeteroES Lab Server-0.1.0-lf1-20261012-r4-Linux.tar.gz` | 124822424 | `52910dd09b66516c964439c61d9c1d28b7429fd885ac1374a63e28f23869307e` |

Published to the running lab's download page, then downloaded in full through the fixed public
address `https://lab.heteroes.site`; size and SHA-256 were compared with this receipt
(`download-check-r4.txt`).

## 3. Real GPU run through the public address only

`scripts/check-public-replay.py` makes the device's advertised private address one nothing listens
on, so the worker agent cannot use the private route and falls back to the lab's public compute
address with `--no-bulk`. RTX 5070 Ti, Recipe v1, workload `arith16`, one device that is both
coordinator and worker.

| Public compute address | Generations x candidates | Result | Candidates committed by the worker | Parent-weights changes | Verified replays | Whole-weights downloads |
|---|---|---|---|---|---|---|
| https://russell-pdas-shaft-trailers.trycloudflare.com | 4 x 4 | COMPLETED | 16 | 3 | 3 | 0 | 
| https://compute.heteroes.site | 4 x 4 | COMPLETED | 16 | 2 | 2 | 0 | 

The first row is the temporary Quick Tunnel (`public-replay.json`); the second is the fixed name on
the owner's Cloudflare domain (`public-replay-named-domain.json`). A parent-weights change needs one
replay; a generation whose rewards are all equal is a no-op and needs none.

## 4. Lesson recorded: a fixed domain rejects Python's default signature

The first attempt on the fixed domain hung: Cloudflare answers `403 error code: 1010` to the default
`Python-urllib` User-Agent, which every Python client of the system used, while a Quick Tunnel link
did not. All clients now send `HeteroES-Worker/1` (commit "Identify every HTTP client as HeteroES"),
and the Worker app sends `HeteroES-Worker/0.1`.

## What this does NOT show

- Only one device, which was both coordinator and worker: no second machine, no different network
  and no Windows worker took part. The public route was forced by address, not by distance.
- A worker that falls too far behind would stop with `needs_private_route` (unit-tested, not run on a GPU).
- The Windows installers were built (Wine/NSIS) and downloaded, never installed or run; they are unsigned.
- No ordinary person walked through the apps on a normal desktop.
- Large downloads through a Cloudflare tunnel on a free plan are fine for a few friends; they are not a
  distribution plan (object storage such as R2 would be).
