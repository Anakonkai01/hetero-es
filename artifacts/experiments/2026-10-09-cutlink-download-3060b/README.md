# cut-link while the second 3060 downloads the weights (09/10/2026)

Written by the AI, **not reviewed by the owner**. Scenario `cut-link` of `scripts/failure_campaign.py --remote-worker third --third-replay never`: the 3060 (another city) must DOWNLOAD every new parent (988 MB over a link measured at about 21 Mbit/s, so about 6 minutes), and the packets from its Tailscale address are dropped on the 5070 Ti for 15 s, starting 3 s after generation 0 is published. N = 8, 3 generations, `cot_l1_q128`, reference hash `a2123e79…` from `../2026-10-09-failure-campaign-remote-3060b/rep1/reference`.

## Result (one run)
Passed: the run ended well, same final weights as the reference, the cut really happened (`exercised`).

## What this does NOT show (read this)
* **The cut was too short to break anything the worker could see:** the worker log has no error during the 15 s of the cut. The TCP download survived (packets were sent again); the first errors (`Connection refused`, 58 in 120 s) come AFTER the coordinator had finished (it ended at +162 s). So "a broken download resumes or restarts" was NOT tested. A cut of 60 to 120 s would be needed.
* **The coordinator finished all three generations before the 3060 had downloaded the first new parent:** the 3060 made 2 candidates of generation 0 and then only downloaded. The 5070 Ti did the rest alone. The run is therefore also an example of why a 21 Mbit/s worker must not download each parent.
* After the coordinator ended, the worker kept retrying for at least two minutes without giving up (it was stopped by the clean-up).
* In practice a remote worker would not download the weights of every generation; the download is the fallback (late join, a replay hash mismatch, a start from a checkpoint). This test is of that fallback only. One run, no repetition.
