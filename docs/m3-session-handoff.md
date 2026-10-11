# Session handoff — 2026-10-11

**Execution resumed:** see [local completion progress](local-lab-progress.md).
The owner authorized M3a–M6 local implementation, removed GPU-hour/total-run
budget caps and authorized persistent private sudo credentials. Retrieve the
private file referenced in that progress document when an authorized task needs
sudo; never copy its contents into source control or evidence. Historical budget
figures below remain usage records, not current limits. Cloud stays deferred.

Read this first when resuming product work. The owner requested session closure,
documentation, local commits and preservation of state. No GPU campaign was run
during closeout. Documentation is English; communicate with the owner in Vietnamese.

## Active source and reading order

| Track | Active checkout | Branch | Implementation/evidence commits before closeout |
| --- | --- | --- | --- |
| A, numerical runtime | `/home/pc5070ti/projects/hetero-es-m3-runtime` | `feat/m3-native-worker` | `9ef0d91`, `a499a2e` |
| B, product | `/home/pc5070ti/projects/Hetero-ES-LLM-m3` | `feat/m3-worker-desktop-ux` | `58023a2`, `a102f86` |

Run `git log -1 --oneline` in each checkout for its final closeout commit. Local
archive `manifest.json` and `git-bundles.json` record the final source revisions.
No push, merge, tag or public installer release was performed.

1. A: `HETEROES_LLM_MASTER.md` (canonical design), then
   `HETEROES_LLM_STATUS.md` (current verified truth, latest blocks first).
2. B: [accepted roadmap](lab-roadmap.md), [M3 implementation](m3-local-worker-ux.md)
   and [Worker owner guide](worker-desktop-guide.md).
3. [Windows hardware evidence](evidence/2026-10-11-m3-native-windows/README.md),
   [packaging/UX evidence](evidence/2026-10-10-m3/README.md) and
   [closeout state](evidence/2026-10-11-m3-session-close/state.json).

Original M2 checkouts `hetero-es-integration` / `feat/m2-agent-runtime` and
`Hetero-ES-LLM` / `feat/m2-cloud-control` were left clean. Research checkout
`hetero-es` was untouched. The older `/home/pc5070ti/projects/handoff.md` describes
the 06/10 research phase; its new pointer leads here. Preserve its historical body.
Earlier per-step approval text is historical: the owner subsequently authorized
implementation and this closeout. Continue within that scope; do not expand it to
pushes, cloud charges, driver changes or replacing friends' environments.

## Delivered and verified

M1 lab operations and M2 local agent/control/recovery are implemented. Actual
R2/EC2/HTTPS cloud acceptance is pending; the owner has no cloud accounts and
explicitly deferred cloud work. M3a implements a native Worker desktop and shared
Vi/En, light/dark/system, responsive web/desktop UX. M3b Server installers,
M4 parallel scheduling, M5 model/dataset expansion and M6 remain planned.

Private Windows per-user NSIS, Linux AppImage and portable Linux archive are built.
The Worker installs isolated pinned Python/wheels/model, qualifies numerically,
pairs, awaits approval and needs explicit owner ON. Every new boot starts OFF.
Closing keeps the tray process; OFF/Quit cooperate with shutdown. Credentials use
safeStorage; Linux requires a working desktop keyring and rejects plaintext storage.

Native Windows qualification and GPU trial passed on **Thao's RTX 3060**, Windows
11 build 26200, driver 617.42; Python 3.12.15, torch 2.13.0+cu132, NumPy 2.5.3,
transformers 5.17.0. Worker `desktop-5a5bc7e5fcaf`, device
`2281352a495f42d989567cfcb3cd5b3c`, display `thao_nguyen_3060`.

| Run | Result and scope |
| --- | --- |
| `95b347701aea49bdbd5b4978d1982a78` | COMPLETED G2/N4; Linux 5070 Ti coordinator, Windows committed all 8 candidates and verified replay. Separate one-GPU Linux baseline with the same experiment ID matched every seed/reward, both generation records/child hashes and actual final checkpoint bytes. |
| `8047b923e2d1427895045b384d130247` | CANCELLED G2/N32; owner OFF during a live lease, 5 results, zero applied updates, confirmed shutdown and all reservations released. Windows owner's ON preference restored afterward. |
| `45d72973ddf243fdb8d9a46d2e9a670f` | Earlier unintended legacy M1 integration-test run, local 5070 Ti only; CANCELLED, fully stopped. Keep its evidence and budget charge. |

Final distributed/baseline checkpoint SHA-256:
`04934b82565441a60ea7f9e8389b35885cf7066c77d226de3701f625d29e1bb8`.
Windows runtime file bytes match A; normalize separators when comparing the
source manifest, rather than comparing OS-dependent raw tree hashes.
This proves one tested Windows combination, not all hardware or LLM learning gains.

Existing validation: A **2041 passed / 100 skipped** with CUDA hidden and a caught
birth-identity mutation; B **73 backend / 11 desktop / 22 mock behavior groups**,
build/lint, real responsive browser and actual packaged Linux CPU/setup checks.
Linux coordinator/baseline GPU results do **not** qualify the Linux desktop installer.

## Current services and private state

At closeout, dispatch is **held**, queue **0**, reservations **0**, local CUDA
process query empty. Native Windows Worker is **ONLINE/ON**; preserve the owner's
choice. Legacy `5070ti`, `3060` (Quang) and `3060-thao` (WSL) are OFF/OFFLINE.
The temporary campaign coordinator is OFF/stopped. No friends' machine was
contacted by SSH during this closeout.

- Web: `http://100.110.165.40:5181`; CPU API: `http://100.110.165.40:8002`.
- API source is B M3; its Python environment remains original B `.venv-backend`.
- Product config/credentials/process records/logs: `~/.config/heteroes-m2/`.
  Metadata: `~/.config/heteroes-m2/state/product.sqlite` (**21 experiments**).
- Local coordinator token/config: `~/.config/heteroes-m3-campaign/`;
  original M2 agent config: `~/.config/heteroes-m2-agent/`, unchanged.
- Raw trials, ledgers, checkpoint files and outbox:
  `~/.local/share/heteroes-m3-campaign/` (about 6.5 GiB).
- Original M1 config: `~/.config/heteroes-integration/`; old M1 services on
  5173/8000/8765/8766 were not restarted after the host reboot.
- Local admin password was set to the owner's requested value. Retrieve it from
  the private credential file; never put passwords/tokens into Git or tool output.
  Existing remote access credentials remain private; do not rewrite them.

Services are manually started, not guaranteed across a reboot. To restore only
the held CPU preview, from B M3:

```bash
python3 scripts/start-m3-preview.py
python3 scripts/check-native-windows.py --phase status
```

The second command authenticates and reads status; it does not start compute.
The first checks agent mode, dispatch hold and tracked PID birth before starting.
Do not invoke the GPU phases to rediscover already completed trials: they refuse
overwriting evidence. GPU phases require both `--gpu` and
`HETEROES_GPU_ACCEPTANCE=1`; legacy `test:integration` defaults to observe-only.

## Local archive and recovery precautions

Session archive: `~/.local/share/heteroes-session-archives/2026-10-11-m3-close/`,
private directory (0700), copied credentials/config and database files (0600).
It contains both source Git bundles, three independently copied installer files,
consistent SQLite online-backup snapshots with `integrity_check=ok`, campaign
logs/config/evidence and a SHA-256 manifest. Final bundle revisions/verification
are in `git-bundles.json`. Database snapshots include product metadata, campaign
ledgers and the agent outbox; live WAL files were not copied as backups.

Large stopped-campaign files are **hardlinked** into this same-disk archive to
avoid duplicating several GiB. They preserve filenames against source deletion,
but share file contents. Never modify checkpoint files in place. This archive
does not protect against disk failure and is not an off-machine/cloud backup.
The previous integration backup remains intact. About 11 GiB was free before
closeout; check `df -h` before downloading another isolated runtime/model.

Keep live credential files in place. Restoring metadata requires a planned idle
maintenance window, stopping the owning API and validating a copy before swapping
the database; do not replace a live SQLite file. Git bundles can reconstruct new
checkouts without GitHub. Installer downloads remain private Tailscale links on
the Workers page; build-time `nativeWindowsGpuVerified:false` in older immutable
evidence is historical and superseded by the dated hardware trial, not edited.

## Budget and next action

GPU-hours are conservative upper bounds: cumulative **1.144965250143793 / 2.0**;
M3a **0.1231332501437929 / 0.25**, remaining lower bound **0.1268667498562071**.
M2 cloud reserve **0.083799** is unchanged. Windows qualification was charged the
owner-reported full 120-second upper bound. Read `budget.json` in the hardware
evidence before any new campaign; do not reset counters.

**Next: validate the packaged Linux Worker on a real GPU**, not another core-only
Linux baseline. The owner explicitly identified this as the next required test.
Start by checking desktop/keyring, available disk, GPU ownership and topology.
Use the portable archive on this host if FUSE 2 remains unavailable; AppImage needs
a separate supported environment. Fresh isolated setup → numerical qualification
→ pairing/approval → owner ON → real candidates/replay/reference comparison →
OFF/Quit and restart-OFF observations. Record immutable dated evidence and usage.

Avoid enrolling a Linux desktop alias for the physical 5070 Ti while also allowing
its existing coordinator identity to reserve that same GPU: identity-level
reservations alone do not establish distinct physical resources. Choose an
explicit test topology and check leases/processes before compute. No Linux GPU
campaign was started by this closeout. Remaining Windows gates include clean-image
installation, single-instance/tray/Quit/restart-OFF and network/coordinator outage
observations. Cloud remains deferred until the owner changes that decision.
