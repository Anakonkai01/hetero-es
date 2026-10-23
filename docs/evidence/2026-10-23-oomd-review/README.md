# oomd review: recovery-point upload loop (2026-10-23, 10:00-10:20, Claude)

Read-only review requested by the owner after the overnight soak. Nothing was changed on the live services.

## What happens on every generation

- Default backup policy is `{"interval": 1, "retain": 3}` (`backend/validation.py:70`, `backend/store.py:336`,
  `runtime/src/heteroes/product/agent.py:328`), so the coordinator captures a recovery point after **every** generation
  (`product/recovery.py:100`).
- Locally a point is cheap: hard links to the published parent/child weights and the selected weights, plus a SQLite
  backup of the ledger and `usage.sqlite`. In the soak run directory four points share five ~988 MB weights files
  (link counts 3-5); the run's 5.6 GB is mostly weights + `export/`, not point copies.
- The expensive part is `product/cloud_sync.py`, a thread in the worker service that wakes every 30 s:
  1. `verify_point` re-reads and SHA-256s **every** file of the point (2-3 weights files + selected weights, ~3-4 GB);
  2. `upload` sends each object the lab does not have yet. The local lab storage plans `mode: "single"`
     (`backend/local_storage.py:271`), and the agent then does `stream.read(size)`: the whole ~988 MB child weights file
     is read into Python memory before the PUT;
  3. the lab writes the object to `storageDirectory = /mnt/Archive-2tb/heteroes-local/artifacts/lab-storage-20261012`,
     an NTFS disk mounted through FUSE (`fuseblk`, ntfs-3g), then verifies it again.
  On any error the cycle `break`s and the next cycle 30 s later starts again at step 1, with no backoff.

## Measurements

- Lab DB (`~/.config/heteroes-m2/state/product.sqlite`), soak run `44e65d7b…`: a new point upload began about every
  2 min from 02:29 (generations 4, 11, 17, 19, 24, 30, 39, 50, then 64 after the kill …). Almost all stayed `PENDING`
  (superseded before finishing); only three became `READY` (generations 178, 185, 192). The last begins at 03:44.
  Whole lab storage: 298 READY objects (~102 GB in the DB, 96 GB on disk) + 145 PENDING (~46 GB in the DB).
- Archive is now full (16 GB free, 100%), so the soak's final point can never upload (`cloud-sync.json`:
  `PENDING / HTTPError`, rewritten every 30 s, last at 10:14).
- With **no run active**, the worker service reads **56-67 MB/s** (`/proc/<pid>/io` rchar: 6 GB in 90 s, 56 MB/s over
  60 s; 1.29 TB since its 02:50 restart, 3.2 GB of it from disk, the rest page cache).
- Its cgroup holds **9.1 GB file cache, 0.2 GB anonymous** (`memory.stat`); `memory.current` 9.4 GB. PSI now is 0.
- At the kill (02:50:07, generation 62) oomd reported the service at 7.3 GB with `user@1000.service` pressure 53 %.
  The lab server runs in a tmux scope under the same `user@1000.service`, so its FUSE writes count in the same parent.

## Conclusion (strong hypothesis, not proven)

At 02:50 the soak was producing a generation every ~24 s while the agent was hashing ~3-4 GB per attempt, holding a
~1 GB buffer per upload and pushing ~1 GB every ~2 min into a slow FUSE disk. That fits a page-cache/writeback stall in
`user@1000.service`; the worker service was the largest cgroup and was killed. No PSI/memory.stat sample exists from
02:45-02:50, so the cause is not proven. The 30 s re-verify loop described above is a separate, **confirmed** bug: it
runs now, with no run active, because the Archive is full.

## Proposed fixes (not implemented; owner decides)

1. `cloud_sync`: upload only the newest point, skip superseded ones; back off on errors (e.g. 30 s → 30 min); stop
   retrying a finished run's non-final points; verify once per point, not on every attempt.
2. Stream uploads (multipart or chunked PUT), never `read(size)` of a whole weights file.
3. Make the default backup interval time-based or larger for long runs (e.g. every 10 min / 25 generations); local
   points can stay frequent because they are hard links.
4. Do not put lab recovery storage on the NTFS/FUSE Archive disk, or cap its share (quota is 200 GB on a disk that also
   holds personal data).
5. Then repeat a soak with the sampler capturing PSI and `memory.stat` (anon/file/dirty/writeback) every 10 s.
