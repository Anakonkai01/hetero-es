# GTX 1660 SUPER candidate6 qualification: PASS

Predeclaration: [README.md](README.md). Run 2026-10-21 09:06–09:17 +07 on `heteroes-worker-1660s`
(Ubuntu 26.04.1, kernel 7.0.0-38, driver 595.91.07, Turing compute capability 7.5, 6 GiB).

| Step | Result | Receipt |
| --- | --- | --- |
| Candidate6 CLI install (unchanged private installer, fresh worker home) | PASS, runtime `aa74bad820b9`, `cpu_guard.py` `150ac9fd...ea95d` | `install.log`, `install-1660s.sh` |
| `HETEROES_GPU_ACCEPTANCE=1 heteroes-worker selftest --device cuda` | PASS | `selftest.log` |
| Nine-case guarded-decoder probe vs committed 5070 final receipts | 9/9 all fields equal | `1660s-product-guard.json/.log`, `comparison.json` |

Installed model `model.safetensors` SHA256 equals the recipe pin (`fdf756fa...fb7fe`). The parent was checked
(`dfbfa65c...a93d9`) after transfer. Free space on `/` went from 211.5 GB to 202.5 GB.

Compared fields per evaluation: descriptor, completion texts, completion hash, restored parent hash, input IDs,
attention mask, full new-token arrays, evaluation FP32 and perturbed FP16 weight hashes; plus decoder source,
old recipe hash, recipe and plan. `compare.py` (committed here) reproduces the earlier Windows and Quang PASS
results, and nine in-memory single-field corruptions of the 1660S receipt are all rejected.

Selective CPU reference calls `[0, 2, 0, 4, 1, 2, 3, 0, 2]` (14 total), identical to native Windows. CPU threads 8.
Peak GPU allocation 2.854 GiB. Available RAM after each candidate 40.0–41.1 GiB.

Diagnostic timing for the nine evaluations (not a benchmark): 1660S 178.8 s total (rollout 148.8 s, CPU
reference 24.4 s); 5070 29.1 s; Quang 3060 45.0 s; Windows 3060 42.1 s. In a synchronous generation the
1660S will be the slowest worker by roughly 4x versus a 3060.

## Operator error, retained

The first probe attempt (`probe-attempt1-missing-input.log`) stopped before any GPU work with
`FileNotFoundError`: the three dataset `.jsonl` files referenced by `dataset.json` had not been copied.
They were copied (hashes equal to the local originals) and the unchanged probe was run once more. No result
was discarded; the failed attempt produced no output file. A first install upload also arrived empty over
SSH stdin and ran nothing; it was re-sent with scp.

## What this does NOT show

Not the managed 50-generation acceptance, audits, outage/retry or a universal numerical bound. The 1660S has
not joined or been approved in any lab. Its earlier unstable-PCIe history was not re-tested by this short run
(PCIe reported gen 1 x16 at idle). No public/live change, merge or release.
