# File-backed Recipe v3 datasets: 1 GB and 10 million rows (2026-10-20)

Owner decision: datasets "well above 3 MB", default 1 GB per file and 10 million rows, changeable by the platform
administrator (`GET/PUT /api/v1/platform/dataset-limits`). Format 3 (`heteroes.v3.data.build_file_dataset`) keeps one
canonical JSON Lines file per split; the split hash is that file's SHA-256 and the dataset document stays a few hundred
bytes. Rows are read by position on demand. The seeded 80/10/10 split is the same permutation as the in-memory format
(test). The lab takes signed uploads (`/api/v1/datasets/upload-plan`), builds the dataset by streaming
(`/api/v1/datasets/uploads/{id}/build`), and lets a device fetch only the split files its assignment pins. Devices put the
split files beside the document; recovery points carry them. The web import uses this route for v3 files above 3 MB.

Scale probe (`scale_probe.py`, CPU, Archive disk, 10,000,000 generated rows, 1.17 GB source):

| | build | open + verify | 3 batches of 32 | one epoch-shuffle batch | peak memory |
| --- | --- | --- | --- | --- | --- |
| `scale-10m-before-buffering.json` | 900 s | 3.4 s | 0.65 s | 1.2 s | 231 MB |
| `scale-10m.json` (digests buffered) | 186 s | 8.5 s | 1.0 s | 2.1 s | 393 MB |

The first build opened a duplicate-check file once per row; buffering the digests cut the build to 186 s. Split sizes:
8M / 1M / 1M rows (1.42 GB / 178 MB / 178 MB of canonical JSON).

Checks: `runtime/tests/v3/test_v3_file_dataset.py` (splits equal to the in-memory format, CSV and pre-split input,
epoch coverage, duplicates up to whitespace, limits, tampered split or document, device download over HTTP, recovery
point with and without split files), `backend/tests/test_large_datasets.py` (upload, build, experiment, transfer
grants, limits, only an administrator changes them), and the end-to-end CPU run
`test_managed_run_with_a_file_backed_dataset_and_a_python_reward_and_rule`. Mutation: runtime 9/9, backend 5/5.

## What this does NOT show

- No GPU run and no real 1 GB upload through a browser; the probe built the dataset directly on disk.
- An epoch-shuffle batch shuffles all train positions (2.1 s for 8M rows) every generation; it is not cached.
- Validation and test splits are read whole by the coordinator's tracker; a split of millions of rows would make every
  validation slow (that is the researcher's choice of split sizes).
- The open+verify and batch times of the two probes differ although that code did not change: the second run shared
  the disk and CPU with other work; they are single measurements.
