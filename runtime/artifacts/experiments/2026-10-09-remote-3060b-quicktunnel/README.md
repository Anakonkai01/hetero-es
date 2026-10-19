# The second 3060 through a Cloudflare Quick Tunnel (09/10/2026)

Written by the AI, **not reviewed by the owner**. Same run as `../2026-10-09-remote-3060b/` (T2, N = 24, 3 generations, workload `cot_l1_q128`, experiment id `c1v2`, replay always) but the second borrowed 3060 (another city, WSL2) reached the coordinator at a PUBLIC https address of a Cloudflare Quick Tunnel (`cloudflared` 2026.10.0, started by the owner by hand at ~14:37 on the 5070 Ti, stopped by the AI after the run; the address in `tunnel-url.txt` is dead). `run.sh` is the command (the secret and the address come from environment variables), `summary.json` is made by `scripts/summarize_benchmark.py`.

## Results (one run)
* **Ended well, 0 failures** on both workers, no internal errors. Final weights hash `a02a640b…` = the hash of every earlier B0 run of this experiment id (`identical_rewards_and_hashes: true`).
* The 3060 did 19 jobs and the 5070 Ti 53 (72 = 3 x 24); the 3060 made no weights download (replay).
* Steady-state T = 119.7 s (B0: 151.6 s in `../2026-10-09-three-machines`, 2 runs; Tailscale run of the same machine: 126.3 s). One run each: the difference between 119.7 and 126.3 s is not established as real.
* **The public address required the token:** without it the address answered HTTP 401 (checked during the run); after the tunnel was stopped it answered HTTP 530 (no tunnel).

## What this does NOT show
* One run, no interval; nothing about speed differences between the two paths.
* Not tested: a long run, a tunnel that drops in the middle (the coordinator and worker retry logic was not exercised on purpose), many workers, the 100-second answer limit of the tunnel on a slow request, a hostile client. The weights file (about 1 GB) did NOT cross the tunnel (replay): the tunnel's terms limit large files and its body limit is 100 MB.
* Cloudflare decrypts the traffic: it could see the token, the rewards and the candidate descriptors.
* The token is a shared secret, not an identity of a machine (per-device identity is only planned).

## Things that went wrong (kept)
* `attempt1-health-check-401-stuck-bench/` + `attempt1-run.out`: the run stalled because `cluster_runner.wait_health` called `/v1/health` without a token and treated the 401 as "not up". Fixed in `scripts/cluster_runner.py` (401 counts as up), tests in `tests/c1/test_cluster_runner_health.py`.
* **A secret reached the evidence:** `plan-n24.json` of both attempts recorded the command line of the remote worker, including the one-time token. The value was replaced by `<REDACTED>` in those two files before the commit (the token was already useless: the tunnel and the coordinator were stopped). `cluster_runner` should redact secrets itself (TODO).
* `cluster_runner` starts the coordinator with `--allow-unauthenticated` always: without a token, a public address would give anyone access. Here a token was set and the server enforced it.
