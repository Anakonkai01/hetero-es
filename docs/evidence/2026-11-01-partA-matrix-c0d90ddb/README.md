# Part A intermediate matrix at src-c0d90ddb

All receipts and logs identify source `src-c0d90ddbe800ef358e86d8b7fd09e9f11c0abdb25395e6cc79bf8b11a5eb72d5`
(commit 570b4b90). Every copied top-level check log was verified against its receipt SHA-256 before archival.

Local: noise/ES 572 passed and strict suite 1,636 passed, both zero skips. Three trained parity probes, throughput,
int8 memory and phase trace passed. All 12 mutation groups passed. The first fault batch used the backend interpreter,
which lacks PyTorch for final CPU replay; those three failures are retained. Rerunning faults with the runtime
interpreter passed normal/fault comparison, 600-generation soak and int8 lifecycle (3/3).

Both packaged Linux apps built and imported, but the package byte guard rejected dirty documentation/kept CPU receipts.
This is A-024; its guard fix needs a new source receipt.

WSL: noise/ES 572 passed, zero skips. The strict suite had 1,555 passed, two failed, 79 SM120-specific cases explicitly
deselected and zero skips. The failures are historical non-strict FP16 output assertions, A-025. The independent SM86
capture is archived separately. Three strict parity and three performance checks passed on the RTX 3060.

## What this does NOT show

This is not final Part A acceptance: package and the WSL FP16 assertions failed on this source. It is not evidence for
native Windows, PostgreSQL, OIDC, MinIO, MiniCloud deployment or learning. Later source changes require fresh receipts.
