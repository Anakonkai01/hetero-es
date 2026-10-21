# r11 candidate7 — tail-aware scheduling, liveness and elastic membership (predeclared)

Replacement for candidate6. It carries ADR-009 (`feat/r11-scheduling-elastic`, CPU gate 23/23 ALL PASS at `37723d6`,
receipts `../2026-10-21-scheduling-elastic/`). The numerical code is unchanged: same decoder `hf_fp32_cpu_guard_v1`,
noise, update and recipe identities.

Planned:
- **Build:** `BUILD=lf1-20261021-r11-candidate7 scripts/build-apps.sh` into a fresh Archive directory (UUID
  10443D1F443D094C checked). Then commit the refreshed desktop resources.
- **Prepare:** `publish-local-installers.py --prepare-only`. Nothing is published.
- **Compare:** every runtime source file in the Worker and Server archives must equal the source. The new
  `product/membership.py` must be in both.
- **Checks:** a source-copy packaging check, plus packaged Linux Server and Linux Worker checks. Their scratch trees go
  on the Archive volume, because the system disk has about 10 GB free.

## What this does NOT show

This is not a hardware, Windows or installed-device receipt, and not the 50-generation acceptance. No publication,
deployment, merge or push. Older candidates and their evidence are left untouched.
