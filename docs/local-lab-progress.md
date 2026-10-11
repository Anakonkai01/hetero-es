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

## Milestones and acceptance evidence

| Milestone | Implementation | Acceptance |
| --- | --- | --- |
| 0: secondary-disk preservation | Implemented | Passed: independent encrypted archive, 140 files restored and hashes verified |
| M3a: packaged Linux GPU Worker | Qualification implemented/verified | Actual portable app, fresh isolated Python, real libsecret, 5070 Ti numerical reference passed; candidate/replay/baseline/lifecycle/outage gates pending |
| M3b: local Server/storage | Filesystem backend and CPU Server app implemented | Signed transfers/CAS/manifest-last and actual packaged Linux CPU install/bootstrap/same-origin/manual start/tray/stop/restart passed; Windows and owner walkthrough pending |
| M4: disjoint scheduling/pause | Physical reservation and eligible FIFO implemented | Atomic alias fencing and independent progress verified on CPU; pause/resume and multi-GPU hardware pending |
| M5: model/data/Recipe v2 | Pending | Pinned files, frozen splits/batches, evaluation, local learning trials/export |
| M6: fault/recovery/usability | Pending | Fault campaigns, migration/rollback, fresh-machine and owner walkthrough |

Update implementation and acceptance independently. Unavailable remote hardware
or clean VMs remain explicit pending gates, never substitutes for verified work.

Owner availability update: Quang is unavailable today; Thao has only short usage
windows. No prolonged remote campaign will be scheduled. Continue the 5070 Ti
and CPU work independently; retain multi-machine gates as pending.

Evidence: [foundation checks](evidence/2026-10-11-local-foundation/README.md).
Literature decisions: [ES papers and Recipe v2](es-literature-local-recipe.md).

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
