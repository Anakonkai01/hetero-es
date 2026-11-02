# B10 acceptance mutant target migration

B9 base e3800f61 removed the flat backend shims. The preflight audit found24 of137 mutation targets still pointed to
those old filenames. The first B10 CPU attempt was interrupted before a receipt; a redundant standalone check-all was
also stopped to avoid duplicate work/fixture ports. Neither is accepted whole-suite evidence.

The new acceptance selftest requires every137+ target to exist, match its old text exactly once and produce valid
Python after mutation. Its initial failure is retained. The24 backend mutations now point to the actual API/service/
core owners; indentation and the earlier HTTPException-to-ServiceError boundary change are accounted for. Meanings,
names and count stay the same. Original JSON fixture layout is preserved. Product and numerical source did not change.
All59 acceptance selftests pass; focused controls28 each kill strict-qualification16/16 and GPU-ownership8/8 mutants.

## What this does NOT show

These are CPU mutation/selftest checks, not the final clean same-source37-check matrix. Full CPU/GPU/WSL/native B10
acceptance still follows at the next committed source identity. No private state, credentials, datasets or GPU work is
included. The live lab remains unchanged. The full A->B->C objective is unfinished.
