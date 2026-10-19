# G3 on one machine: a coordinator and two worker processes over HTTP, against a single-process reference (06/10/2026)

**What this is.** The first run of the real distributed runtime: a coordinator process and two worker processes (each its own Python
process with its own copy of Qwen2.5-0.5B-Instruct on the GPU) talking over HTTP on the loopback interface of the 5070 Ti machine,
for two generations of ES with four candidates each. The workers synchronize to the new weights between the generations by
downloading the weights file (full synchronization). The same experiment was then run in ONE process with no network and no ledger
(`reference.json`), and the two are compared.

**What it shows.** For both dispatch policies, B3 (greedy) and B1 (static waves of two), the rewards of all 8 candidates and the
SHA-256 of the weights after each of the two updates are **identical, bit for bit, to the single-process reference**
(`comparison.txt` in each folder: every line EQUAL). So, on this machine: the protocol (lease, result, update record) and the full
synchronization (988,065,536 bytes, hash checked before the model is touched) do not change a single bit of the result, and the choice
of the dispatch policy does not change the numbers (it changes who does what: compare the candidates of each worker in the
`summarize.py` output).

**What it does NOT show.**
- It is not a measurement of speed. Three processes shared one CPU and one GPU, and the noise generation (about 3.7 s per candidate,
  CPU) is the cost; the distributed runs (92.8 s and 96.0 s) were SLOWER than the reference (73.1 s) here. A speedup needs workers on
  separate machines; no claim about B1 against B3 can be made from these runs.
- One machine, one GPU, loopback network, two identical workers: nothing about heterogeneity, the real network or the 1660 SUPER (the
  physical two-node run is not done: see STATUS 0.0).
- 4 candidates, 2 generations, sigma 1e-3, alpha 1e-3, one seed family (`derive_seed("e2e", generation, index)`), 16 prompts: a check of
  correctness, not of learning (the mean reward went from 0.2188 to 0.1719, which means nothing with four candidates).
- No failure was injected in these runs (the failure behaviour is tested with fake workers and real HTTP in `tests/ledger/`).

## Files

| File | What |
|---|---|
| `greedy-b3/`, `wave-b1/` | one run each: `summary.json` and `events.jsonl` of the coordinator, `ledger.sqlite` (the ledger as the coordinator left it), `worker-a.jsonl`, `worker-b.jsonl`, `comparison.txt` |
| `reference.json` | the single-process reference (`scripts/reference_generations.py`) |
| `summarize.py` | prints the numbers quoted here from the raw files |

## How it was run (commit `bb2fcd2` plus the two scripts of the next commit; the code state is also recorded inside the files: `code.git_commit`, `code.git_dirty`)

```
SNAP=~/.cache/huggingface/hub/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots/7ae557604adf67be50417f59c2c2f167def9a775
python scripts/run_coordinator.py --model-path $SNAP --out-dir <dir>/coordinator --weights-dir <published dir> --experiment-id e2e \
    --candidates 4 --generations 2 --alpha 1e-3 --sigma 1e-3 --policy greedy|wave [--wave-size 2] --port <port> \
    --lease-seconds 600 --timeout-seconds 900 --linger-seconds 15
python scripts/run_worker.py --model-path $SNAP --coordinator-url http://127.0.0.1:<port> --worker-id worker-5070ti-a|b \
    --log <dir>/worker-a|b.jsonl --cache-dir <cache dir> --poll-seconds 1.0 --give-up-after-seconds 60
python scripts/reference_generations.py --model-path $SNAP --output reference.json --experiment-id e2e --candidates 4 --generations 2 --alpha 1e-3 --sigma 1e-3
python scripts/compare_generation_runs.py <dir>/coordinator/summary.json reference.json
```

Machine: RTX 5070 Ti, Python 3.12.13, torch 2.10.0+cu128, NumPy 2.4.5, transformers 5.5.0 (the `environment` field of every record).
The recipe hash of every record is `1604737ea1d7203062d641381172899356a261748f754a8f3264019ac1b3f5b1`, the one of the numerical
gate of 06/10; the initial weights hash is `c9118c8a4903c0a84700deeaf7b1929c354dfcf6d6805c08d9afb22cfd5d22c7`, the original model.

## What the first, smaller run found (a 2-candidate, 1-generation smoke run that is not kept as evidence)

The coordinator process exited as soon as it was done, so a worker never saw the `FINISHED` state and polled a closed port for ever.
Fixed: the coordinator lingers (`--linger-seconds`) and a worker exits when it has not heard from the coordinator for
`--give-up-after-seconds`. In the runs kept here both workers ended with `exit: finished`.
