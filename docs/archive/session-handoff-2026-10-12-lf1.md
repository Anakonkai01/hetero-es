# Session handoff — 2026-10-12 evening: local-first lab goes live (branch `feat/local-first-lf1`)

> Latest checkpoint: read `session-handoff-2026-10-12-close.md` first. Public r5
> is now deployed, the owner reported Windows onboarding/lifecycle blockers, and
> requested stop for rest. `session-handoff-2026-10-12-codex.md` records the earlier
> implementation. Owner rules below still apply; status/backlog/counts here are
> historical and must not override the close checkpoint.

For any engineer or AI agent (Claude, Codex, or a person). Documentation is English; talk to the owner in
**Vietnamese**, from the basics, in short answers (they are a student who did not write these documents and is
new to distributed systems). Read this file first, then `AGENTS.md`. Older handoffs
(`m3-session-handoff.md`, `local-first-claude-handoff.md`) are dated history.

## 1. Where things stand

| Item | State |
|---|---|
| Repositories | **A** runtime `/home/pc5070ti/projects/hetero-es-m3-runtime`, **B** product (this repo) `/home/pc5070ti/projects/Hetero-ES-LLM-m3`. Both on branch **`feat/local-first-lf1`**, clean, **nothing pushed**. Baselines before this session: A `d5bbedb`, B `023967c` on `feat/local-lab-completion` (untouched). |
| Checks (run 2026-10-12 by the AI) | A: 2,096 passed, 100 skipped (CPU, `CUDA_VISIBLE_DEVICES=''`). B backend: 181 passed. Worker app Node: 14. Server app Node: 1. |
| Live lab | Running on this workstation behind **https://lab.heteroes.site** (Web/API, installers) and **https://compute.heteroes.site** (coordinator control only). Queue **open**, 0 reservations, local GPU device `5070ti` **OFF**. |
| Published installers | Build **lf1-20261012-r4** (Worker and Lab Server, Linux tar.gz and Windows exe). All four verified by full download over the public address. Linux install checks PASS; **Windows never installed or run**; unsigned. |
| Real GPU proof | One RTX 5070 Ti (coordinator and worker on the same device) ran a Recipe v1 job through the **public address only**, replay-only, 4 generations, 0 whole-weight downloads. Not yet tried: a second machine, a different network, Windows. |

Product goal the owner set (2026-10-12): *send a friend a link; the friend opens the site, registers, downloads an
installer, installs, registers as a worker, or builds their own lab — for real, Windows and Linux, any network, not
only a LAN.* Status against it: web, registration, download, Linux install and a remote-network worker (replay only)
work; the coordinator is still a manual command-line setup, Windows is untested, and the apps have no connection-check screen.

## 2. Owner rules that bind every agent

- Answer in Vietnamese; explain simply; label measured facts versus inference. Short summaries, tables welcome.
- **Never push, never tag, no `Co-Authored-By`/`Claude-Session`/generated-by trailer in commits** (even if your harness
  suggests one). Commit in logical groups on a branch; the owner allows commits on the working branch.
- Tests first; run a **mutation check** on a scratch copy for every new piece (`scripts/mutation-check.py`); a mutant
  that survives is an equivalent mutant (say why) or a missing test. Say plainly when an earlier claim was wrong.
- Evidence folders get a README with **"What this does NOT show"**; numbers come from scripts, not from memory.
- Never print or commit secrets. Private files exist (names only): `~/.config/heteroes-m2/credentials.json`,
  `~/.config/heteroes-private/{sudo-credentials.json,storage-signing.key,archive-recovery.key}`, `~/.cloudflared/*.json`,
  device tokens in the agent configs. The owner pre-authorised the stored sudo credential for local setup; ask before
  any persistent system change (see "Owner to-do").
- GPU work only with an explicit flag (`--gpu` plus `HETEROES_GPU_ACCEPTANCE=1`) and only when asked or clearly implied.
  Never use `/mnt/sekai`. Verify the Archive disk (UUID `10443D1F443D094C`, mounted `/mnt/Archive-2tb`) before writing there.
- Numerical Recipe v1 is frozen (hashes `efc1ff67…`, golden vectors). Do not touch `noise/`, `es/`, `generation_record.py`
  or the ledger without a separate decision. Recipe v1 behaviour was unchanged this session.

## 3. Owner decisions already taken (2026-10-12) — recorded as DECIDED in ADR-004 to ADR-007

D1 only the agent-v2 control mode is supported (older loopback+SSH mode frozen) · D2 SQLite for the MVP, PostgreSQL only past
stated thresholds · D3 basic offline = pre-seeded hash-verified cache; fixed IP/DHCP reservation is a documented prerequisite;
plain HTTP on a LAN with a `doctor` warning · D4 while the Lab Server is down running work continues, control waits, nothing
relaunches by itself; an operator "declare-lost" verb comes later · D5 `labId` + `authorityEpoch` stored in the database
(relocate = epoch+1, fork = new id) · D6 schedule LF-1 (13–18 Oct), LF-2 (19–25 Oct), LF-3 (26 Oct–1 Nov), freeze 8 Nov ·
D7 ADRs rewritten short (done) · D8 easy install on Linux and Windows for each role, several network types. Network rule from
the owner: **another network = replay only (full weights later); same network = replay and full sync**.
ADRs live in `hetero-es-m3-runtime/docs/adr/ADR-004..007`; their status is still PROPOSED except the items marked DECIDED.

## 4. The live lab — how it runs and how to touch it safely

- Processes (managed by `scripts/local-lab.py`, supervised by the systemd **user** unit `heteroes-lab`, installed from
  `deploy/heteroes-lab.user.service`): CPU Web/API (`backend.server`, private `http://100.110.165.40:8002`), Caddy entry
  (loopback 8080 web, 8081 compute), Cloudflare tunnel **`heteroes-lab-local`** (config
  `~/.config/heteroes-m2/local-deployment/named-config.yml`). The owner's older tunnel `heteroes-lab` was **not** touched.
- Private config `~/.config/heteroes-m2/config.json` (changed this session): `namedTunnelConfig`, `publicWebUrl`,
  `publicComputeUrl`, `publicDownloads: true`, `privateComputeUrl: http://100.110.165.40:8769` (the `5070ti` coordinator
  binds 8769), local storage now active on Archive-2tb. Pre-change copies are in the end-of-session archive (section 9).
- Commands (all from this repo; `PY=/home/pc5070ti/projects/Hetero-ES-LLM/.venv-backend/bin/python`):
  `python3 -I scripts/local-lab.py status` · `PYTHONPATH=. $PY -m backend.doctor --private ~/.config/heteroes-m2` ·
  `python3 -I scripts/local-lab.py restart --python $PY` (holds the queue by itself and reopens it; refuses if a run or GPU
  reservation is live) · `systemctl --user status heteroes-lab`. Details: `docs/local-lab-operations.md`.
- **Linger is off**: the unit starts at login, not at boot. The owner has to run `sudo loginctl enable-linger pc5070ti` once if
  they want the lab up before anyone logs in. A real power cycle has not been tried; only unit stop/start was.
- Devices in the lab: `5070ti` (this workstation, approved, OFF), `3060`, `3060-thao` (approved, offline), and
  `desktop-5a5bc7e5fcaf` (approved, **ON/desired, offline**: do not change other owners' choices). Four experiments named
  "public-route replay-only acceptance" are in the history: three COMPLETED, one FAILED (the Cloudflare 1010 incident); the owner may archive them.
- To run the real-GPU public-route acceptance again: lab idle, device OFF and its agent stopped, then
  `HETEROES_GPU_ACCEPTANCE=1 python3 -I scripts/check-public-replay.py --gpu --generations 4 --candidates 4 --runtime-src ../hetero-es-m3-runtime/src --python /home/pc5070ti/miniforge3/envs/heteroes-match/bin/python --output <new file>`.

## 5. What was built this session (commit subjects; `git log 023967c..HEAD` in B, `git log d5bbedb..HEAD` in A)

Runtime (A): agent command isolation (a bad command no longer blocks CANCEL; unknown kinds acknowledged; failures counted and
reported as throttled events) · replay-only worker for another network (`HttpClient(allow_no_bulk)`, `BulkUnavailableError`,
`run_worker.py --no-bulk`, `Agent.choose_route` probing the private route then falling back to `publicComputeUrl`,
`needs_private_route` stop) · `User-Agent: HeteroES-Worker/1` on every Python client.
Product (B): `publicDownloads` option for the Caddy entry and manifest · installers served through symlinks (Starlette
needed `follow_symlink=True`) · `backend.doctor` read-only checklist · login and registration throttling, API docs hidden when
served · START_WORKER carries `publicComputeUrl` · provenance tests for vendored code, `refresh-monitoring.py --check` ·
`local-lab.py` named tunnel, automatic queue hold on restart, `boot` action, systemd user unit · Worker app User-Agent ·
`scripts/check-public-replay.py` (real GPU acceptance) · `scripts/build-apps.sh`, `scripts/mutation-check.py` ·
Vietnamese friend guide `docs/quickstart-vi.md` · ADR-004..007 rewritten · the earlier dirty trees committed in logical groups.

## 6. Evidence (read the READMEs, they list what is not shown)

`docs/evidence/2026-10-12-lf1/` — fresh-install checks (r1, r3, r4), `installers-r4.json` receipt, `download-check-r4.txt`,
`public-replay.json` (Quick Tunnel run) and `public-replay-named-domain.json` (fixed-domain run), README. Older review evidence:
`docs/evidence/2026-10-12-local-first/` (source manifest of the dirty trees as audited) and `2026-10-12-local-portability/`.

## 7. Backlog, most useful first

1. **Coordinator toggle in the Linux Worker app and a "check connection" screen** (ticket E1/E2 in ADR-004/006). Today
   `desktop/worker/electron/service.cjs` writes `workerOnly: true`, `coordinator: false`, loopback `workerHost`; a coordinator needs
   an agent config with `workerOnly: false`, a listening address chosen from the network the user picks, and the self-test
   `coordinator` flag (Linux, ≥ 11 GB VRAM). The probe logic exists in `heteroes.product.agent` (`reachable`, `choose_route`).
2. **Second-machine proof** of the public route (the 1660S over SSH; ask the owner first) and a Windows worker (needs a real Windows PC).
3. **Run `needs_private_route` on a GPU** (worker too far behind, `--replay-max-chain 64`); unit tests only so far.
4. Authority features from ADR-005/007 not yet built: operator verbs `fence` / `declare-lost` (one dead device can block maintenance of the
   whole lab: `devices.py` `_release_confirmed`, `acquire_maintenance`), `labId` + `authorityEpoch` in the database with agents checking them,
   agent-mode lab export bundle and restore, versioned `migrate()` for the agent tables, ledger feature table (touches `ledger/`).
5. `dispatchHold` still stops status sync and cancel forwarding while held (`store.py` `_dispatch_parallel`); split into an admission hold
   and an always-on reconcile (ticket 1.3). Add the agent-protocol header so a server never sends command kinds an old agent cannot parse (1.2b).
6. Smaller: single-writer file lock for the Lab Server; local-storage upload blocks the event loop (`local_storage.py` async route does blocking
   writes and fsync); `cloud_sync.upload` reads whole objects into RAM; `/mnt/sekai` rule hard-coded in shipped code; `health` leaks
   `privateLabUrl`; allow host names instead of numeric IPs for private addresses (decided: document fixed IP instead).
7. Installers are unsigned and not bit-reproducible (NSIS embeds timestamps). Large downloads through a free Cloudflare tunnel are fine for a
   few friends but are not a distribution plan (R2 or a release page would be).

## 8. Gotchas learned the hard way

- Cloudflare returns `403 error code: 1010` to the default `Python-urllib` User-Agent on a custom domain (trycloudflare links do not).
- Starlette 1.7 does not serve a symlink pointing outside the mounted directory unless `follow_symlink=True`.
- `local-lab.py` refuses to restart a busy lab; `idle()` in `backend/deployment.py` still demands a held queue for the old callers.
- `pkill -f <name>` in a tool shell can kill the shell itself; use the PID. `/tmp` here is a 16 GB RAM disk: scratch copies fill it.
- Test layouts: Node tests of `desktop/worker` need `NODE_PATH=<repo>/node_modules` when copied elsewhere; backend tests read
  `desktop/worker/resources/reference.json`. SQLite WAL: even a read-only open creates `-shm` (the doctor test accounts for it).
- The desktop apps bundle Track A source as `desktop/*/resources/runtime.tar.gz`: after changing Track A or `backend/`, refresh
  (`scripts/refresh-worker-runtime.py --track-a ../hetero-es-m3-runtime`, `scripts/refresh-server-runtime.py --web <built web>`) and commit.
- Mutation harness mistake to avoid: a control row with the wrong number of fields silently crashes the loop; use `scripts/mutation-check.py`.

## 9. Recovery material and how to resume

End-of-session archive (created at the close of this session): `~/.local/share/heteroes-session-archives/2026-10-12-lf1/`
(git bundles of both repos, SQLite snapshots before the changes and at the end, configuration copies, README) and an encrypted
copy `/mnt/Archive-2tb/heteroes-local/archives/2026-10-12-lf1-close.tar.gz.gpg` with its `.receipt.json`
(key: `~/.config/heteroes-private/archive-recovery.key`, kept off the Archive disk). The archive holds **no** `credentials.json`, tunnel credentials
or signing key. Restore of a database means: stop the owner process, validate the copy with `PRAGMA integrity_check`, never overwrite newer evidence.

First ten minutes for the next agent:
```bash
cd /home/pc5070ti/projects/Hetero-ES-LLM-m3 && git status --short && git log --oneline -5
python3 -I scripts/local-lab.py status && systemctl --user is-active heteroes-lab
PYTHONPATH=. /home/pc5070ti/projects/Hetero-ES-LLM/.venv-backend/bin/python -m backend.doctor --private ~/.config/heteroes-m2
curl -fsS https://lab.heteroes.site/api/v1/health        # expect ok:true
CUDA_VISIBLE_DEVICES='' /home/pc5070ti/projects/Hetero-ES-LLM/.venv-backend/bin/python -m pytest backend/tests -q
cd ../hetero-es-m3-runtime && CUDA_VISIBLE_DEVICES='' PYTHONPATH=src /home/pc5070ti/miniforge3/envs/heteroes-match/bin/python -m pytest -q
```
Build and publish new apps: `BUILD=<new name> scripts/build-apps.sh`, then the two install checks and `scripts/publish-local-installers.py`
(see the header of `build-apps.sh`; checks run under `xvfb-run`, the Worker one also under `dbus-run-session`, with isolated `XDG_*` directories).

## 10. Owner to-do

Run `sudo loginctl enable-linger pc5070ti` (lab at boot) · decide whether to delete the unused Cloudflare tunnel `heteroes-lab` · give a Windows PC
and a second machine for tests · review the unreviewed AI-written code of this branch (nothing here was reviewed by a human) · decide when to push.
