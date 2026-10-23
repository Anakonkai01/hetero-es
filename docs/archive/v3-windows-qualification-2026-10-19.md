# Native Windows v3 qualification protocol — 2026-10-19

Written before the native Windows GPU runs. The owner selected Windows on the
RTX 3060 machine for r11 acceptance. This stage qualifies native runtime behavior;
installer installation/uninstallation is a subsequent, separately recorded test.

Reuse the fixed model, rows, scoring, seeds, antithetic population, two generations,
three weight spaces, two HTTP workers, forced audits and independent CPU replay
from v3-gpu-qualification-2026-10-19.md. Extract the same numerical runtime source
at `0bbf881` as the Linux/WSL receipts, without modifying the existing desktop
installation or its environment. The existing pinned private CPython 3.12.15 has
Torch 2.13.0+cu132, Transformers 5.17.0 and NumPy 2.5.3. Add PEFT 0.21.2,
Accelerate 1.15.0 and psutil 7.2.2 to a new, qualification-only dependency directory.

Each native cell uses `v3_gpu_acceptance.py run --gpu` and the owner-authorized
HETEROES_GPU_ACCEPTANCE gate. Use fresh run directories. Private runtime, source,
ledgers and state remain under LocalAppData/HeteroES-v3-20261019 on the system
filesystem. C currently has only about 3.4 GiB free. Put published weight files and
worker weight caches in new directories on D using NTFS junctions; validate D's
volume identity before writing: Volume{ac23c91d-438a-4344-8929-39fdc433c858},
NTFS, HDD_2TB. Do not use other disks. The probe's only execution changes are this
bulk-path option and slash normalization of relative source-file paths for
cross-OS source hashing. Numerical documents and algorithm are unchanged.

Compare each completed native receipt against the existing 5070 Ti receipt in
2026-10-19-v3-gpu: exact source-file bytes, recipe/plan, candidate IDs, raw texts,
rewards, both child hashes; all 8 audits must match and CPU replay must pass.
Preserve any first failure and report its boundary. No mismatch is reward zero.
No failed result is overwritten by a retry.

Resolve the r11 wheel reports on their actual target OS: Linux and native Windows,
using the existing exact dependency pins plus the three explicit additions above.
Reports are input to build-worker-profile.py, never handwritten generated profiles.
No r11 release or server switch is published by this qualification. A fresh Windows
installer needs sufficient system-disk space; reusing the existing interpreter for
this runtime test does not prove fresh installer behavior.

## What this does NOT show

No installer acceptance, live enrollment/approval change, lab deployment or learning
benefit. Two local workers are not a heterogeneous network run. The same sample-size
and no-op subset/LoRA limitations from the paired GPU protocol apply.
