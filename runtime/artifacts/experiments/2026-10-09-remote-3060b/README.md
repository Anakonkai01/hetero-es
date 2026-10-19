# A real remote worker: the second 3060 in another city (09/10/2026)

Written by the AI, **not reviewed by the owner**. First run of the runtime with a worker that is not on the owner's network: the 5070 Ti (coordinator + worker) and the SECOND borrowed RTX 3060 (a friend's PC in another city, WSL2), reached through Tailscale (a relay, "sin"), not through the LAN. `run.sh` is the command, `run.out` its log, `summary.json` is made by `scripts/summarize_benchmark.py` over `bench/`.

## Setup
Condition T2 at N = 24 candidates, 3 generations, workload `cot_l1_q128`, CUDA noise engine, FP32, chunk 64, experiment id `c1v2` (the same as `../2026-10-09-three-machines/`, so the final weights must equal those of its B0 runs). The 3060 catches up with each new parent by replay (`--third-replay always`): no 1 GB weights file crosses the link. The admission profile passed to the benchmark is the one of the FIRST 3060 (same GPU model); the second 3060 was not profiled.

## Results (one run)
* **Ended well, 0 failures** on both workers (`failures: 0`), 430 s for the three generations.
* **Same weights as the earlier B0 runs:** final weights hash `a02a640b…2dac` = the hash of `../2026-10-09-three-machines/bench/n24-B0-r1` (both read from the `final_weights_sha256` of the two `summary.json` files). A worker in another city, reached over a relay, gave the same rewards as the 5070 Ti for what it computed.
* **Work split:** in generation 0 the 3060 held 7 of 24 candidates; over the run the 3060 did 22 jobs and the 5070 Ti 50 (72 = 3 generations x 24 candidates).
* **Speed:** steady-state T = 126.3 s against 151.6 s for B0 (`../2026-10-09-three-machines`, 2 runs): about 1.20 times faster than the 5070 Ti alone, against 1.29 with the first 3060 on the home wifi (2 runs). One run; no interval.
* The 3060 did 0 downloads of the weights (`syncs: 0`); the 5070 Ti synchronized twice (2.1 s).

## What this does NOT show
* One run: no interval; a difference between 1.20 and 1.29 is not established as real.
* Only the Tailscale path (a relay), not the public Internet: the Cloudflare Quick Tunnel test was NOT run (the harness refused the command that opens the tunnel; it needs the owner's decision).
* No failure was injected (a link cut, the worker killed) on this machine; no long outage of the coordinator.
* Equality of results is measured for this workload and two GPU models (both 3060s are the same model); it is not guaranteed for other GPUs.
* Identity of the machine: nothing checks that the worker is the machine it says it is (per-device identity is planned, see `docs/planning/`).
