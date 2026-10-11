# Session handoff — 2026-10-11 monitoring close

This is the current operational entrypoint. Documentation is English; communicate
with the owner in Vietnamese. Both active M3 checkouts use
`feat/local-lab-completion`. Implementation/evidence commits are A `9ff2b9c` and
B `28a3c31`; documentation-only close commits follow them. Exact final heads are
in the new private archive's `git-bundles.json`. Nothing has been pushed/merged/tagged.

## Read first

1. Track A `HETEROES_LLM_MASTER.md` (design) and `HETEROES_LLM_STATUS.md` (truth).
2. [Local completion progress](local-lab-progress.md),
   [resource monitoring design](resource-monitoring-design.md),
   [UI/live process guide](ui-monitoring-guide.md).
3. [Latest monitoring acceptance](evidence/2026-10-11-monitoring/README.md),
   [earlier UI acceptance](evidence/2026-10-11-ui/README.md),
   [foundation/hardware qualification](evidence/2026-10-11-local-foundation/README.md).
4. [ES literature and frozen Recipe v2 decisions](es-literature-local-recipe.md).
   This is a specification for pending experiments, not replicated learning gains.

| Track | Checkout | Current branch |
| --- | --- | --- |
| A, numerical runtime | `/home/pc5070ti/projects/hetero-es-m3-runtime` | `feat/local-lab-completion` |
| B, product | `/home/pc5070ti/projects/Hetero-ES-LLM-m3` | `feat/local-lab-completion` |

Original M2/research checkouts are not the active product source. Preserve their
state. Older dated handoffs/archives are historical; do not reinstate their
branch names, hard GPU budgets or outdated implementation claims.

## Owner instructions and next work

Owner authorized local M3a–M6 implementation and persistent private sudo access.
GPU-hour and total-run caps are removed. Explicit owner contribution, physical
GPU ownership, numerical contracts and technical failure/shutdown timeouts remain.
Cloud is deferred. Do not push, merge, tag, replace drivers or modify existing
Python/Conda environments as part of this continuation.

The latest priority is comprehensive Web/Worker/Server UI and resource monitoring:
Overview/Detail, readable fonts, CPU/RAM/disks/network/processes/sensors, GPU
metrics, persistent energy and generation/candidate/seed information. That
revision is implemented and locally verified. Next review the actual UI with the
owner, then finish the local Linux portable Worker leased-candidate/replay/
reference/lifecycle/outage trial and real GPU pause/resume. Use fresh dated
receipts, preserve numerical v1, and stop the current monitoring Agent before
reusing its enrolled identity. UUID alias fencing does not make one card two GPUs.

Quang was unavailable today and Thao only has short windows. Do not depend on a
long remote campaign. Windows sensor parity/new native UI, real disjoint multi-
GPU acceptance, M5 model/data/evaluation/export and remaining M6 fault/usability
are pending. No learning gain or new hardware gate is inferred from CPU/UI tests.

## Delivered and accepted

- M3b CPU Server/local checkpoint storage and M4 physical reservations, eligible
  FIFO and verified generation-boundary pause/resume are implemented. CPU pause/
  resume matches uninterrupted weights. Live preview storage remains **none**;
  a fresh Server creates local recovery storage during setup.
- Shared Vi/En, light/dark/system and Standard/Large UI includes home/auth,
  dashboard, workers, generation/candidate/seed/attempts and artifacts. Host Detail
  is Linux `/proc`/hwmon; Windows currently has basic fixed CIM CPU/RAM and NVIDIA
  observations, with fuller Windows sensors pending.
- CPU package RAPL and GPU driver power are measured; nested CPU core domains are
  excluded from totals. No whole-machine meter or separate DRAM counter is present
  on this host. Whole-machine AC is unavailable, not an invented CPU+GPU total.
- Energy SQLite survives monitor restart, deduplicates component identities and
  supports Session/Today/This month/Lifetime with coverage. Gaps are not filled,
  past unobserved energy is not reconstructed, and host energy is not job billing.
- Final checks: A **2,060 passed/100 skipped**, monitoring/Agent **24**;
  B backend **99**, Worker Node **12**, Server Node **1**, fleet **2**;
  Web lint/all three builds; **52** live page layouts, **48** monitor layouts,
  **26** desktop fixture/theme cases. Actual published Linux apps opened in
  Electron/Xvfb; fresh CPU Server verified real CPU power/detail, bootstrap,
  same-origin Web/API, tray/stop/restart and parent lifetime.
- Current installers **monitor-20261011-r2**: Worker and Server Linux portable
  archives and Windows per-user NSIS. All four HTTP sizes/hashes verified in
  [the receipt](evidence/2026-10-11-monitoring/installers.json). Windows execution
  of this revision and ordinary desktop walkthroughs remain pending.

Historical acceptance remains intact: Thao's native Windows RTX 3060 qualification
and G2/N4 distributed run `95b347701aea49bdbd5b4978d1982a78` matched the separate
Linux baseline (all seeds/rewards, both child hashes and actual final weights).
Final SHA256 `04934b82565441a60ea7f9e8389b35885cf7066c77d226de3701f625d29e1bb8`.
Cancellation run `8047b923e2d1427895045b384d130247` confirmed OFF/drain/release.
See [historical Windows evidence](evidence/2026-10-11-m3-native-windows/README.md).
These qualify the tested older build, not the new UI or all Windows hardware.
Local Linux numerical qualification passed in the foundation trial; leased
candidate/replay/lifecycle/outage acceptance for its portable app is still pending.

## Live services, private state and storage

At this close: web/API and one monitoring Agent remain running. Dispatch **held**,
**21** historical experiments preserved, **0** reservations, local contribution
**OFF**, and no local GPU compute. Preserve other owners' contribution choices.

| Item | Location |
| --- | --- |
| Web / CPU API | `http://100.110.165.40:5181/` / port `8002` |
| Product configuration, credentials and PID/birth records | `~/.config/heteroes-m2/` |
| Product SQLite | `~/.config/heteroes-m2/state/product.sqlite` |
| Owned monitoring Agent config/PID/log | `~/.config/heteroes-private/ui-local-agent/` |
| Monitoring Agent state/outbox | `~/.local/share/heteroes-ui-local-agent/` |
| Persistent energy | `~/.local/share/heteroes-power/energy.sqlite` |
| Read-only CPU publisher | `heteroes-rapl.service`, `/run/heteroes-power/rapl.json` |
| Latest review logs/private pre-cutover backup | `~/.local/share/heteroes-monitoring-review/` |
| Historical campaign/config | `~/.local/share/heteroes-m3-campaign/`, `~/.config/heteroes-m3-campaign/` |
| Original Agent config (not the running monitor) | `~/.config/heteroes-m2-agent/` |
| Sudo credentials/storage signing config | `~/.config/heteroes-private/` |

Read passwords/tokens privately when needed; never print them or include them in
Git, command arguments or public evidence. The sudo credential file is already
authorized for later sessions. Use subprocess stdin. The archive recovery key
`~/.config/heteroes-private/archive-recovery.key` is separate from the ciphertext.

Archive-2tb UUID **10443D1F443D094C**, mounted `/mnt/Archive-2tb`; project files are
under `heteroes-local/`. Verify UUID before any write; a missing mount must never
fall back to root. Never use `/mnt/sekai`. Live SQLite, credentials and executable
runtimes stay on ext4. Root had about **100 GiB** free at close; check current free
space before installing new runtimes/models. Historical learning checkpoints
moved to Archive-2tb and retain their original path through a directory symlink.
Earlier duplicate M1 restore-trial weights were removed after hash verification;
restore that stopped trial from the preserved older backup before using it again.

## Resume commands and ownership

From B, inspect rather than restart services that are already alive:

```bash
git status --short
git log -1 --oneline
findmnt -n -o UUID,TARGET -T /mnt/Archive-2tb
curl -fsS http://100.110.165.40:8002/api/v1/health
systemctl is-active heteroes-rapl.service
```

After reboot, once mount/held queue/ownership are checked:

```bash
python3 scripts/start-m3-preview.py
```

This helper restores only CPU API/Web and refuses untracked listeners. The root
RAPL service is enabled separately; its fixed reviewed installation commands are
in the monitoring design. Worker and Server monitors remain unprivileged.

The single monitoring Agent uses the existing `5070ti` device. Read its saved PID
and `/proc/<pid>/stat` birth field (post-final-`)` fields index 19; zombie is not
alive). **If it is alive, do not start another.** If stopped, confirm held dispatch,
zero reservations and local enabled/desired OFF before running:

```bash
PYTHONPATH=/home/pc5070ti/projects/hetero-es-m3-runtime/src CUDA_VISIBLE_DEVICES='' PYTHONNOUSERSITE=1 /home/pc5070ti/miniforge3/envs/heteroes-match/bin/python -m heteroes.product.agent run --config /home/pc5070ti/.config/heteroes-private/ui-local-agent/config.json
```

Run in foreground or record the new PID/birth securely if launching as a managed
background process. New boots start OFF. Do not replay old campaign Agent state
or launch this Agent beside a portable Worker owning the same enrolled identity.
GPU qualification/trial commands require their explicit GPU opt-in; session
resume/status inspection must not silently become a training run.

## Current archive and recovery

New private local archive:
`~/.local/share/heteroes-session-archives/2026-10-11-monitoring-close/`.
Independent encrypted copy:
`/mnt/Archive-2tb/heteroes-local/archives/2026-10-11-monitoring-close-independent.tar.gz.gpg`.
Use their receipts to verify creation/restoration. Public state/snapshot evidence
is in `docs/evidence/2026-10-11-monitoring-close/`; the final ciphertext receipt
is beside the encrypted file and copied into the private local archive. The final
Git heads are recorded in that local archive's `git-bundles.json`.
Contents include both final Git
bundles, consistent current SQLite backups (including energy/outbox), private
configuration, four current installers, service files and source/evidence guides.
Private files are 0600 under 0700 directories. The recovery key is not included
in its encrypted archive and must be retained separately for disaster recovery.

Preserve the original `2026-10-11-m3-close` local archive and independent encrypted
Archive-2tb copy: they contain older campaign/checkpoint recovery payloads. The new
archive supplements those payloads; it does not replace or rewrite old acceptance.
No remote/off-machine backup is claimed. Installer public links/manifest are
ignored by Git: recreate them from the archived installer receipt after restoring
files to their recorded paths, then verify full HTTP hashes.

Git bundles are tested by fresh bare clone/fsck and final branch/head comparison.
SQLite snapshots use the online backup API plus `integrity_check`, not copied
live WAL files. Restoring live databases requires an idle maintenance window and
stopping their owning processes; validate a restored copy before replacing files.
Archived process/boot records are evidence, not instructions to reuse old PIDs or
force contribution ON. Preserve credential permissions and stored signing keys.
