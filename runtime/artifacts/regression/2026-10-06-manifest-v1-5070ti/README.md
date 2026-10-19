# First record with the manifest (format 2) on the RTX 5070 Ti, 2026-10-06 (step 9)

Question: does the real script, at the commit that freezes manifest v1, write a recipe whose hash is the one that was rebuilt offline
from the format-1 evidence of both machines?

Script: `scripts/run_one_candidate.py` at commit `588fa71fe24824d27c76b256757ed29f3f7fbba0` (run with `--seed 0 --sigma 1e-3 --repeat 2`,
the same model, environment and machine as `../2026-10-05-one-candidate/`: RTX 5070 Ti, conda env `ai`, Python 3.12.13, torch 2.10.0+cu128,
NumPy 2.4.5, transformers 5.5.0). `pytest tests` with the real model gave 535 passed on the same tree.

## Files

| File | What it is |
|---|---|
| `5070ti_format2.json` | the record, format 2: environment, code, model, noise self-test, recipe, recipe hash, descriptor, two runs |
| `comparison_format2_vs_format1.txt` | selected lines of the comparison with the format-1 records of the 5070 Ti and of the 1660 SUPER |
| `SHA256SUMS` | checksums of the files of this folder |

## Result

| Check | Result |
|---|---|
| noise self-test (five golden chunks) | passed, about 5 ms |
| recipe hash | `1604737ea1d7203062d641381172899356a261748f754a8f3264019ac1b3f5b1`, equal to the hash rebuilt offline from the format-1 records of the 5070 Ti and of the 1660 SUPER |
| hashes of the weights: original, perturbed, restored | `c9118c8a...`, `8aa3eb9af895cb4a...`, `c9118c8a...` (as before) |
| rewards: base, candidate, restored | 0.25, 0.3125, 0.25 (as before) |
| repeat of the two runs | identical |
| descriptor | experiment `regression`, generation 0, index 0, seed 0, parent weights `c9118c8a...` |
| generation config | hash of the set values `b55cff86...`; the raw hash `05744820...` is stored too |

## Limits

- This is a record of ONE machine. The format-2 script was not run on the 1660 SUPER; the comparison with the 1660 SUPER uses its format-1
  record, whose recipe is rebuilt from its own fields by the comparison script.
- `git_dirty` is true: the unrelated untracked notebook `notebooks/floating_point_testing.ipynb` (and this folder itself, written by the run).
- The recipe, the descriptor and the self-test are only as good as the tests of `heteroes.manifest` and `heteroes.noise.selftest`; the pinned
  recipe hash in `tests/test_manifest.py` was produced by the same code (a regression guard).
