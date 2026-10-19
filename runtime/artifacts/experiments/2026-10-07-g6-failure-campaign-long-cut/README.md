# G6: the link cut for 80 s (07/10/2026)

`failure_campaign.py --scenarios cut-link --cut-seconds 80`, N = 8, 8 generations, FP32 chunk 16, lease 20 s (the setting of `../2026-10-07-g6-failure-campaign/README.md`). The packets from the 1660S were dropped right after generation 0 was published, for 80 s; the
experiment ran on, in 144 s, with the 5070 Ti alone (all 64 attempts are the 5070 Ti's). The 1660S worker logged one transport error (`GET /v1/job` timed out: it had not even begun to download), waited, came back after the cut, synchronized three
times to the weights of the generations that were then current, and exited with `finished`. **Final weights = the undisturbed reference** (`7069c8c4...`, `reference/`).
It shows a worker that rejoins after a long outage without the coordinator doing anything. It does not show the resumable download (the cut came before the download began; see `../2026-10-07-g6-failure-campaign-resume-download/`). One run.
