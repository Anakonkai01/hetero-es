# Same candidate on the RTX 5070 Ti and the GTX 1660 SUPER, 2026-10-06 (step 7)

Question: does one logical candidate (seed 0, sigma = float32(1e-3), the 16-prompt workload) give the same result on the two
physical machines? This is the cross-machine same-candidate regression of `docs/numerical-contract.md` section 9, for one candidate.

The 5070 Ti side is the evidence of the folder `../2026-10-05-one-candidate/` (files `5070ti.json` and `5070ti_process2.json`, SHA-256
`0bec6340...` and `e6349b38...`). This folder holds the 1660 SUPER side and the comparison.

## What was run on the 1660 SUPER (`heteroes-worker-1660s`)

- Same commit as the 5070 Ti run: `30275cd5c5186849f7168eba9b3f2c9a892664aa`. The commits were not pushed, so they were sent as a
  `git bundle` (`scp`, SHA-256 `1834c401...` checked on both sides), fetched into a new local branch of the repository there and
  checked out detached at `30275cd`. The tree there was clean (`git_dirty` is false in both JSON files).
- `pytest tests` with the real model (`HETEROES_QWEN_PINNED_PATH`, `HETEROES_QWEN_PATH`): **404 passed in 471 s** (`1660s_pytest.txt`).
  The 5070 Ti gives the same 404 passed (107 s).
- `scripts/run_one_candidate.py --seed 0 --sigma 1e-3 --repeat 2`, twice in two separate processes (`1660s.json`, `1660s_process2.json`).
- The model is the same file on both machines: `model.safetensors` is the blob `fdf756fa7fcbe7404d5c60e26bff1a0c8b8aa1f72ced49e7dd0210fe288fb7fe`
  in both Hugging Face caches (the blob name is the SHA-256 of the file).

| | RTX 5070 Ti | GTX 1660 SUPER |
|---|---|---|
| compute capability | 12.0 | 7.5 |
| driver | 595.91.07 | 595.91.07 |
| Python | 3.12.13 | 3.14.4 |
| torch / CUDA | 2.10.0+cu128 / 12.8 | 2.13.0+cu132 / 13.2 |
| NumPy | 2.4.5 | 2.5.2 |
| transformers | 5.5.0 | 5.17.0 |

## Files

| File | What it is |
|---|---|
| `1660s.json`, `1660s_process2.json` | records of the two processes on the 1660 SUPER |
| `1660s_pytest.txt` | the log of `pytest tests` there |
| `comparison_5070ti_vs_1660s.txt` | report comparing `5070ti.json` with `1660s.json` (see the note on the comparator) |
| `SHA256SUMS` | checksums of the files of this folder |

## Result

The whole result of the candidate is identical on both machines.

| Check | Result |
|---|---|
| model revision, tokenizer revision, dtype, schema hash `0b21250e...`, workload hash `cad822bc...`, engine version, chunk size, seed, sigma | equal |
| hash of the original weights (`c9118c8a...`) | equal |
| hash of the perturbed weights (`8aa3eb9af895cb4a...`) | equal |
| hash of the weights after restore | equal to the original, on both |
| outputs of the 16 questions: base model, candidate, restored model | **equal, text for text, in all three evaluations** |
| rewards: base, candidate, restored | 0.25, 0.3125, 0.25 on both |
| repeats: 2 runs in each of the 4 files | identical |
| all four pairs (each 5070 Ti file against each 1660 SUPER file) | every "must be equal" line equal |

Predictions of the candidate (the same on both): `[41, 48, 54, 156, 6298, 670, 509, 580, 8409, 1520, 8097, 10, None, None, None, None]`.

Time of one run in seconds (first run of each file) and GPU memory (peak over the whole run minus the allocation before it):

| step | 5070 Ti | 1660 SUPER |
|---|---|---|
| snapshot | 0.24 | 0.65 |
| perturb (includes the CPU noise generation) | 3.7 | 9.2 |
| restore | 0.14 | 0.49 |
| hash of all weights (done 3 times) | 0.6 | 4.2 |
| evaluation of the 16 questions | 0.8 to 1.1 | 7.9 to 10.2 |
| GPU memory more than before the run | 73 MiB | 72 MiB |

## Note on the comparator and the generation config

- `comparison_5070ti_vs_1660s.txt` was made by `compare_candidate_records.py`, a script that is **not in the repository yet** (it was
  written for this step and is waiting for review).
- The first version of the comparator compared the hash of the whole `generation_config` dict and reported a DIFFERENT line
  (`05744820...` on the 5070 Ti, `8fb3597a...` on the 1660 SUPER). The cause is the library, not the model: transformers 5.17
  adds four keys whose value is `None` (`assistant_ensemble_weight`, `max_cache_len`, `speculation_type`, `use_mtp`) and stores its
  own version (5.5.0 and 5.17.0). The set values are identical on both machines: `do_sample` true, `temperature` 0.7, `top_k` 20,
  `top_p` 0.8, `repetition_penalty` 1.1 and the token ids.
- The comparator was therefore changed to compare the SET values (without `None` and without the library version) and to print the raw hash only as
  information. **This rule was decided by the AI after it saw the difference; it is pending the owner's approval.** The records are unchanged:
  the full dict is stored in each JSON file, so anybody can apply another rule.

## Limits

- One candidate (seed 0, sigma 1e-3), 16 prompts, greedy decoding: equal outputs here do not prove that all candidates agree
  (other seeds and sigmas, longer outputs, other prompts were not run).
- Two x86_64 Linux machines with different GPUs, different Python, torch and transformers versions (table above); not a universal guarantee.
- The 5070 Ti files have `git_dirty` true (an unrelated untracked notebook, see the README of `../2026-10-05-one-candidate/`).
- Files left on the 1660 SUPER in `/tmp`: `heteroes_step7.bundle`, `step7/`, `step7_pytest.log`, `step7_run.log`. Its repository there has a new
  local branch `feat/perturb-restore-update` and is on a detached HEAD at `30275cd`; the old branch `feat/canonical-noise-engine` is untouched.
