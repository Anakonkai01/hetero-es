## Architecture review update — 2026-10-12

Current entrypoint: [Claude review handoff](local-first-claude-handoff.md).
Code changes from the earlier continuation are preserved uncommitted; coding,
installer builds, service cutover, GPU campaigns and cloud work are paused.
The [proposal](local-first-architecture.md) and ADR-004..007 are PROPOSED choices.
The owner, rather than the audit author, approves architecture decisions.

Audit CPU results: runtime 2,074 passed/100 skipped; backend 109 passed/one failed
(vendored Windows collector provenance expectation). Earlier `20261012-r2`
same-host GPU harness accepted boundary resume and v2 export/reload within its
scope; the Quick receipt accepted CPU transport/auth/private Range only. Neither
is a fresh native package, remote GPU, multi-job or learning-gain acceptance.
No new installer replaces `monitor-20261011-r2`. See the
[audit receipt](evidence/2026-10-12-local-first/audit.json) for source hashes.

Operating snapshot: 21 historical experiments, held dispatch, zero reservations,
local contribution OFF and no GPU workload. Web/API and Quick Tunnels remain
running; monitoring Agent is stopped. Private local storage configuration is
prepared, but live backend reports no active recovery storage. No restart/cutover
was made during review. Earlier paragraphs below are dated history.

## Session close — 2026-10-11

Current operational entrypoint: [session handoff](m3-session-handoff.md). Both M3
branches are `feat/local-lab-completion`; implementation/evidence heads A `9ff2b9c`,
B `28a3c31` precede documentation-only close commits recorded in the new bundle
manifest. Local and independently encrypted monitoring-close archives supplement
older immutable recovery payloads. Public snapshot evidence is under
`docs/evidence/2026-10-11-monitoring-close/`; final encrypted restore receipts are
beside the archive and in its private local directory. Check these before assuming
completion.
Services remain running, queue held, contribution local OFF, zero reservations
and no local GPU compute. Full local access/GPU budget override persists; cloud
is deferred. Nothing pushed. Resume the newest handoff rather than older budget,
branch or pending-feature paragraphs below.

# Local lab completion — 2026-10-11

Owner authorization: implement M3a through M6 locally; cloud is deferred. Both
tracks use `feat/local-lab-completion`, based on A `80be3d6` and B `6027d5a`.
Existing numerical v1 identities and historical evidence remain immutable.

## Active decisions

- GPU-hour caps and the 30-minute total-run budget are superseded. Retain
  GPU opt-in, technical stall/network/shutdown timeouts and usage measurements.
- Storage is **Archive-2tb**, UUID `10443D1F443D094C`, under
  `/mnt/Archive-2tb/heteroes-local`. Never use `/mnt/sekai` for this project.
  Live SQLite, isolated executable runtimes and credentials remain on ext4.
- Owner authorized persistent sudo credentials for local lab machines. Retrieve
  the private file `~/.config/heteroes-private/sudo-credentials.json`; never put
  its values in Git, arguments, logs or evidence. It is separate from existing
  remote access credentials. Directory/file permissions are 0700/0600.
- Server starts manually, closes to tray; autostart is optional. Local artifact
  storage does not require R2 accounts. No push/merge/tag or driver/environment
  replacement is authorized by this scope.
- Math has verifiable answers. Dataset import accepts single-file seeded
  80/10/10 splitting or three already split files. Preserve built-in v1 tasks.
- Recipe v2 keeps one-point population z-score ES and adds cosine sigma;
  GRPO training is outside this implementation. Learning claims require held-out
  metrics, multiple seeds and exported-model reload checks.

## Latest resource monitoring continuation

The owner requested fuller power/energy readings and Task Manager/GNOME/btop/
nvitop/W&B/distributed monitoring patterns. Track A `9ff2b9c` adds bounded Linux
host detail, optional GPU detail and private persistent component energy. Track B
shares Overview/Detail across Web/Worker/Server, increases labels/text, adds a
Large text preference and deduplicated fleet power/energy. See
[design and source references](resource-monitoring-design.md) and
[verified evidence](evidence/2026-10-11-monitoring/README.md).

Final CPU checks: A 2,060 passed/100 skipped; B 99 passed; monitoring/Agent 24;
Worker Node 12, Server Node 1, fleet aggregation 2. Web lint/three builds passed.
UI checks cover 52 live page layouts, 48 dedicated monitor layouts and 26 desktop
fixture/theme cases with both views, text sizes and widths. Published Linux apps
were extracted/opened in Electron/Xvfb; fresh CPU Server also verifies real CPU
power/detail, bootstrap, same-origin web, tray/stop/restart and parent lifetime.
The current local downloads are `monitor-20261011-r2`. Windows installers were
built; new native UI and hardware sensor parity remain pending. No GPU campaign.

One OFF monitoring Agent now runs current Track A source. Its private PID/birth
record/config/log remain `~/.config/heteroes-private/ui-local-agent`. The read-only
RAPL publisher is enabled as `heteroes-rapl.service`; normal Agents remain
unprivileged. Energy SQLite stays on ext4 and persists across Agent restarts.
Whole-machine AC requires a real meter; no meter is configured, no fake estimate
or historical backfill is shown. All 21 original experiment bodies/snapshots and
owner contribution flags were compared to the private pre-cutover SQLite backup.
The live API retains `storageMode: none`, dispatch held and zero reservations.

## Milestones and acceptance evidence

| Milestone | Implementation | Acceptance |
| --- | --- | --- |
| 0: secondary-disk preservation | Implemented | Passed: independent encrypted archive, 140 files restored and hashes verified |
| M3a: packaged Linux GPU Worker | Qualification implemented/verified | Actual portable app, fresh isolated Python, real libsecret, 5070 Ti numerical reference passed; candidate/replay/baseline/lifecycle/outage gates pending |
| M3b: local Server/storage | Filesystem backend and CPU Server app implemented | Signed transfers/CAS/manifest-last and actual packaged Linux CPU install/bootstrap/same-origin/manual start/tray/stop/restart passed; Windows and owner walkthrough pending |
| M4: disjoint scheduling/pause | Physical reservation, eligible FIFO and checkpoint-boundary pause/resume implemented | UUID alias fencing, epoch/drain barriers and identical pause/resume weights verified on CPU; real GPU pause/resume and multi-GPU hardware pending |
| M5: model/data/Recipe v2 | Pending | Pinned files, frozen splits/batches, evaluation, local learning trials/export |
| M6: fault/recovery/usability | Pending | Fault campaigns, migration/rollback, fresh-machine and owner walkthrough |

Update implementation and acceptance independently. Unavailable remote hardware
or clean VMs remain explicit pending gates, never substitutes for verified work.

Owner availability update: Quang is unavailable today; Thao has only short usage
windows. No prolonged remote campaign will be scheduled. Continue the 5070 Ti
and CPU work independently; retain multi-machine gates as pending.

Evidence: [foundation checks](evidence/2026-10-11-local-foundation/README.md).
Literature decisions: [ES papers and Recipe v2](es-literature-local-recipe.md).

## Earlier UI continuation (superseded by the monitoring update above)

Comprehensive UI redesign implemented: public home/auth, dashboard/navigation,
light/dark/system themes, actual hardware/energy/history measurements, experiment
generation/candidate/seed inspection and Worker/Server layouts. New local Linux
portable and Windows NSIS downloads are on the homepage. See the
[UI guide](ui-monitoring-guide.md) and [acceptance evidence](evidence/2026-10-11-ui/README.md).
Track A continuation is commit `0fb8e16`; inspect Track B HEAD for its UI commit.
No push was performed. The original M3 archives remain historical; the monitoring-close
archive described in the current handoff captures the later final heads.

M4 pause/resume is now implemented in both tracks, with a verified generation
checkpoint barrier, drain/epoch fencing and unchanged deterministic CPU baseline.
Hardware pause/resume and simultaneous multi-GPU acceptance are still pending.
Large data placement is UUID-guarded; live state stays on ext4. CPU runtime suite:
2,052 passed/100 skipped; backend: 96 passed. These are not GPU learning claims.

The live preview preserves 21 historical experiments, held dispatch and device
owner choices. Its existing recovery storage configuration is unchanged/none.
One isolated local 5070 Ti Agent supplies real telemetry while contribution is
OFF. Do not start a second Agent for that same enrolled device. Cloud deferred;
M5 and the remaining M6 hardware/usability gates remain uncompleted.

## System-disk cleanup

On 2026-10-11 the root filesystem had approximately 4.9 GiB free. Removed
34 verified duplicate weights from the completed M1 restore trial (31.29 GiB)
and 54 duplicate Worker download-cache files (2.60 GiB). Canonical run weights,
the full integration backup and the old trial's metadata remain available.
The old trial must be restored from its backup before being used for recovery.

Relocated all 69 retained historical learning checkpoints (63.49 GiB logical,
65 unique objects) from `~/.cache/heteroes/learn-ckpt` to
`/mnt/Archive-2tb/heteroes-local/artifacts/historical-learning-20261008/learn-ckpt`.
Source and destination hashes were verified before removing the root copies.
The original directory is now a symlink, so historical paths still resolve when
Archive-2tb is mounted. Root now has approximately 102 GiB free (78% used).
Receipts are in the foundation evidence directory; unrelated caches and active
Python environments were left in place.

## Recovery key

Encrypted secondary archives use a random key in
`~/.config/heteroes-private/archive-recovery.key` on the original ext4 disk.
The key is stored separately from the archive and must accompany recovery from
another machine through a private channel. Do not commit or put it beside the
ciphertext on Archive-2tb. Receipts expose checksums and verification totals only.

Use `scripts/archive-local-session.py --help` for creation and independent
verification. It requires the selected disk UUID, copies file contents rather
than preserving source hardlinks, authenticates the encrypted stream, checks
every restored file and refuses replacement of an existing archive.
