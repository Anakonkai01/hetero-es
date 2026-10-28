# Real release of the run cancelled before its coordinator accepted it (2026-10-20, session 5 close)

After the owner restarted Quang's WSL: Windows C: had **6.9 GB** free (supporting the out-of-space diagnosis for the earlier
I/O errors). Two superseded test runtimes inside the WSL disk were deleted (≈9.8 GB) so that reinstalling reused freed
blocks; the candidate4 one-line installer then completed, the CPU self-test passed and C: stayed at 6.9 GB
(`quang-cli-reinstall-candidate4.log`).

With the candidate4 isolated lab running, Quang's CLI device (`heteroes-worker run`, it reports its cancelled-assignment
marker) and the 5070 Ti desktop Worker both polled. The candidate3 run `ec1c8f27…`, stuck in STARTING since its
cancellation, became **CANCELLED** and both devices' allocation cleared — the real-world check of 595faa1 (CPU test
evidence in `2026-10-20-cancel-before-coordinate`). Everything was then stopped again; all contributions are OFF.

## What this does NOT show

No new experiment ran. Quang's C: remains low (6.9 GB); avoid further large writes into that WSL until space is freed.
