# One ES candidate end to end on the RTX 5070 Ti, 2026-10-05 (step 6)

Question: does one candidate, run with the code of the package, behave as the earlier evidence says it must?
Load the pinned model, snapshot, evaluate the base model, perturb (seed 0, sigma = float32(1e-3)), evaluate the
candidate, restore, check the bits, evaluate again.

Script: `scripts/run_one_candidate.py` at commit `30275cd5c5186849f7168eba9b3f2c9a892664aa`.

```
python scripts/run_one_candidate.py --model-path <HF snapshot 7ae55760...> --seed 0 --sigma 1e-3 --repeat 2 --output <file>
```

It was run twice, in two separate processes (`5070ti.json`, `5070ti_process2.json`), each time with `--repeat 2`
(the same candidate twice in one process). So the same candidate ran four times in total.

## Environment (the same in both files)

RTX 5070 Ti (compute capability 12.0), driver 595.91.07, conda env `ai`: Python 3.12.13, torch 2.10.0+cu128,
NumPy 2.4.5, transformers 5.5.0. Model `Qwen/Qwen2.5-0.5B-Instruct` at revision
`7ae557604adf67be50417f59c2c2f167def9a775` (loaded from the Hugging Face cache snapshot directory, which is named
after the revision; the tokenizer comes from the same directory), FP16. Hash of the model's generation config:
`05744820d4b6cd4285ba6cc04c48f5a6a547151423389144554e2c558eb4a70e` (it contains `repetition_penalty` 1.1).

## Files

| File | What it is |
|---|---|
| `5070ti.json` | record of the first process: environment, code, model, two runs, `repeat_identical` |
| `5070ti_process2.json` | the same, second process |
| `SHA256SUMS` | checksums of the files of this folder (checked with `sha256sum -c`) |

## Result

| Check | Result |
|---|---|
| Schema hash = `0b21250e331398a266785dc473da3a8b8f5e8f98fa15e9044637d742eb7845ec` | equal |
| Workload hash = `cad822bc1e65a9ec37d948e5415cff22c70f96500e2043e6299bbdd5cea0b8d5` (the one recorded by the 2026-09-29 probes) | equal |
| Base model outputs versus `artifacts/probes/2026-09-29/probe_5070ti.json` | equal, text for text; reward 0.25 |
| Whole-model hash of the perturbed weights starts with `8aa3eb9af895cb4a` (the value of the four environments of 2026-10-03) | equal |
| Hash of the weights after restore versus before (`c9118c8a4903c0a8...`) | equal |
| Outputs after restore versus base outputs | equal, for all 16 questions |
| Repeat in one process (both files) | `repeat_identical` true |
| All four runs, over the two processes | identical (everything except the clock and the GPU memory) |

Reward: base 0.25, candidate 0.3125 (5 of 16), after restore 0.25. The candidate changes the output text of 10 of the 16
questions (for example `6292` -> `6298`, `664` -> `670`, `7906` -> `8409`). Predictions:

```
base      [41, 48, 54, 156, 6292, 664, 509, 589, 7906, 1302, 8095, 10, None, 1, None, None]
candidate [41, 48, 54, 156, 6298, 670, 509, 580, 8409, 1520, 8097, 10, None, None, None, None]
```

Time of one run, in seconds (first run of each file; the two files agree within a few hundredths): snapshot 0.24,
perturb 3.7 (includes the CPU noise generation), restore 0.14, hash of all weights 0.6 (three times),
one evaluation of the 16 questions 0.8 to 1.1. GPU memory: 950 MiB before, peak 1023 MiB, so 73 MiB more during the whole
run (this is the peak of the whole run, not the memory used by the restore alone).

## Limits

- One machine only; this is the step 6 evidence, the same script on the GTX 1660 SUPER is step 7.
- One seed (0), one sigma (1e-3), one candidate, 16 prompts: a candidate that happens to score 0.3125 says nothing about learning.
- `git_dirty` is `true` in both files. At the time of the first run the only untracked path was
  `notebooks/floating_point_testing.ipynb` (an unrelated notebook, nothing that the script imports); at the second run
  `5070ti.json` itself was also untracked. No tracked file differed from commit `30275cd`.
- Repeat across processes was checked by running the script twice; there is no comparison tool in the repo yet (the
  comparison above was made with a few lines of Python on the two files).
- The base outputs are the same as on the 1660S according to the probe of 2026-09-29; this run does not show that.
