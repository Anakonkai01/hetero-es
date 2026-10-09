# Failure campaign with the second 3060 as the disturbed remote worker (09/10/2026)

Written by the AI, **not reviewed by the owner**. `scripts/failure_campaign.py --remote-worker third` (new option): the five scenarios with the second borrowed 3060 (another city, WSL2, Tailscale relay, about 94 ms and 21 Mbit/s: `../2026-10-09-remote-3060b/wan-link-measurement.txt`), the 5070 Ti as coordinator and local worker. Long workload `cot_l1_q128`, CUDA engine, chunk 64, N = 8, 3 generations, lease 60 s, the 3060 catching up by replay. `rep1/` is the only repetition; `verdicts.json` there has the verdicts.

## Results (rep1, one run per scenario)
All five passed (`ended_ok`, `exercised`, same final weights as the undisturbed reference run): kill-worker, pause-worker, cut-link, kill-coordinator (SIGKILL with 12 results committed, restarted with `--resume`), kill-coordinator-mid-update (SIGKILL between the write-ahead record and the applied update).

## What this does NOT show
* One repetition only (the earlier campaigns had three). `run.sh` also planned a profile of the 3060 and reps 2 and 3; the profile was stopped (owner: the long tests were not worth it; `profile-3060b.log` is the partial log) and reps 2 and 3 were not run.
* **The cut-link here proves little:** with replay on, the 3060 downloads no big file, so a cut of 8 seconds only delayed small requests; the worker log has no error event. The note in `rep1/cut-link/run.json` says "packets from anakonkai@10.10.10.2 dropped": that is a wrong text of the script (it printed the 1660S address); the rule itself used the 3060's address (`100.99.227.8`, the script's `peer`). The text was fixed afterwards in `scripts/failure_campaign.py`; the evidence file keeps the old text. See `../2026-10-09-cutlink-download-3060b/` for the download variant.
* Equal weights at the end are measured for this workload and these GPU models only.
