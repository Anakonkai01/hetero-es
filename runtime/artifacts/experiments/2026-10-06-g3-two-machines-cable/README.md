# G3 on two physical machines: a coordinator and workers on the RTX 5070 Ti and the GTX 1660 SUPER (06/10/2026)

**What this is.** The first run of the distributed runtime on the two real machines. The coordinator (ledger, canonical weights,
update) and worker `worker-5070ti` run on the 5070 Ti machine; worker `worker-1660s` runs on the 1660S machine. They talk HTTP over a
direct gigabit cable between the two machines (`10.10.10.1` and `10.10.10.2`, one `eno1` port on each; the internet and Tailscale stay
on the other interfaces). Eight candidates, three generations, alpha 1e-3, sigma 1e-3, the 16-prompt workload, a shared token. After
each update the coordinator publishes the weights file (988,065,536 bytes) and each worker synchronizes to it by downloading it (full
synchronization). The same experiment was then run in ONE process on the 5070 Ti with no network and no ledger (`reference.json`) and
compared (`comparison.txt`).

| Folder | Policy | What |
|---|---|---|
| `2026-10-06-g3-two-machines-cable` (this one) | B3 greedy | the main evidence; `comparison.txt`: 13 lines, all EQUAL |
| `2026-10-06-g3-two-machines-cable-wave` | B1 static waves of 2 | same, other policy; 13 lines, all EQUAL |
| `2026-10-06-g3-two-machines-8c3g` | B3 greedy | same experiment over the Wi-Fi of the 5070 Ti (about 3 MB/s, measured with scp): the 1660S did only 2 candidates of generation 0 and was still downloading the next weights when the coordinator finished. Rewards and hashes of the coordinator are EQUAL to the reference, but this run does NOT show full synchronization on the 1660S |
| `2026-10-06-g3-two-machines` | B3 greedy | a first smaller run (4 candidates, 2 generations) over Tailscale; generation 1 was degenerate (all four rewards 0.25, so the update changed nothing and no weights were downloaded): it proves little about synchronization |
| `2026-10-06-g3-cable-attempt1-firewall-blocked` | B3 greedy | a failed attempt: the firewall (ufw) of the 5070 Ti dropped the packets to port 8765 on the cable, the 1660S worker only saw timeouts and did no work; the 5070 Ti worker did all 24 candidates. Kept because the files show the failure; the result is still EQUAL to the reference |

## What it shows
- Both physical workers completed generations. For both policies, the rewards of all 24 candidates and the SHA-256 of the weights after
  each of the three updates are **identical, bit for bit, to the single-process reference** (final weights `7da3a16f…` in the greedy
  run and in the failed attempt, which differ in which machine did which candidate). So the candidates evaluated on the GTX 1660 SUPER
  (Python 3.14.4, torch 2.13, NumPy 2.5.2) give the same rewards as on the 5070 Ti (Python 3.12.13, torch 2.10, NumPy 2.4.5) for the
  same seeds, and the full synchronization does not change a bit.
- Full synchronization works on both workers: the 1660S downloaded the new weights twice per run (transfer 8.5 s, load 4.1 s, hash check
  4.8 s each time) and the hash was the name of the file each time; the worker on the 5070 Ti machine (it shares the disk with the
  coordinator) needs 0.5 to 3 s for the transfer.
- The static waves gave each worker four candidates per generation (12 each); the greedy policy gave the faster worker more (20 and 4).
  Median seconds per candidate on the 1660S: perturb about 9 to 10, rollout about 8; on the 5070 Ti: perturb 3.7, rollout 0.7
  (`summarize.py` prints them).

## What it does NOT show
- No speedup. The distributed runs (303.6 s greedy, 450.4 s waves) were slower than the single-process references on the 5070 Ti
  (223.4 s and 210.3 s; two runs of the same work that differ by 13 s, a measure of the noise between runs, not explained): the
  coordinator spends about 46 s per generation on the update, and the weak worker is much slower per candidate. Whether and when this
  runtime pays off is the question of the scheduling and synchronization work that comes next (C2, C4), not of this run.
- One run per configuration, no repetitions, no statistics. Eight candidates, three generations, one seed family
  (`derive_seed(experiment_id, generation, index)`): a check of correctness, not of learning (the mean reward moves by noise).
- No failure was injected on the physical machines (the failure behaviour is tested with fake workers and real HTTP in `tests/ledger/`
  and in the simulations); no restart of the coordinator.
- The synchronization time depends on the link: over the cable it is about 9 s of transfer plus about 9 s of loading and hash checking
  on the 1660S; over the Wi-Fi of the 5070 Ti it did not finish within a whole run of three generations (about 250 s). The cable, the
  addresses and the firewall rule are not part of the repository (see below).
- The code state is `7dcf07d` with two small uncommitted changes of the scripts at the time (the default directories moved from `/tmp`
  to `~/.cache`; the runs passed explicit options or used the new defaults): `code.git_dirty` is true in the files for that reason.
  The 1660S ran the same commit, with the two scripts copied by hand.

## How it was run

```
SNAP=~/.cache/huggingface/hub/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots/7ae557604adf67be50417f59c2c2f167def9a775   # on the 1660S: the snapshot in its own cache
export HETEROES_TOKEN=<random token>             # the same on both machines; never in an argument or in these files
# 5070 Ti
python scripts/run_coordinator.py --model-path $SNAP --out-dir <dir>/coordinator --experiment-id g3-two-machines-cable \
    --candidates 8 --generations 3 --alpha 1e-3 --sigma 1e-3 --policy greedy|wave [--wave-size 2] --host 10.10.10.1 --port 8765 \
    --timeout-seconds 3000 --linger-seconds 40
python scripts/run_worker.py --model-path $SNAP --coordinator-url http://10.10.10.1:8765 --worker-id worker-5070ti --log <dir>/worker-5070ti.jsonl \
    --poll-seconds 0.5 --give-up-after-seconds 120
# 1660S (over SSH, its own venv)
python scripts/run_worker.py --model-path <snapshot> --coordinator-url http://10.10.10.1:8765 --worker-id worker-1660s --log <file>.jsonl \
    --poll-seconds 0.5 --give-up-after-seconds 120
# reference and comparison, on the 5070 Ti
python scripts/reference_generations.py --model-path $SNAP --output reference.json --experiment-id g3-two-machines-cable --candidates 8 \
    --generations 3 --alpha 1e-3 --sigma 1e-3
python scripts/compare_generation_runs.py <dir>/coordinator/summary.json reference.json
```

The wave run used `--experiment-id g3-two-machines-cable-wave`. The network set-up, outside the repository: a NetworkManager connection
`heteroes-direct` on `eno1` of each machine (`10.10.10.1/24` and `10.10.10.2/24`, no gateway) and, on the 5070 Ti, one ufw rule allowing
only `10.10.10.2` to reach 8765/tcp on `eno1`. The recipe hash of every record is
`1604737ea1d7203062d641381172899356a261748f754a8f3264019ac1b3f5b1` (the one of the numerical gate); the initial weights hash is
`c9118c8a4903c0a84700deeaf7b1929c354dfcf6d6805c08d9afb22cfd5d22c7`. The published weights stay out of the repository
(`~/.cache/heteroes/published`, about 1 GB per generation).

| File | What |
|---|---|
| `coordinator/` | `summary.json`, `events.jsonl`, `ledger.sqlite` (in the two oldest runs the WAL was folded into the file, same rows) as the coordinator left them |
| `worker-5070ti.jsonl`, `worker-1660s.jsonl` | the event log of each worker (steps with timings, syncs, exit) |
| `reference.json`, `comparison.txt` | the single-process reference and its comparison |
| `summarize.py` | prints the numbers quoted here, for this folder and for the wave folder |
