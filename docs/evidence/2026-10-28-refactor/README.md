# Refactor of main: evidence off main, experiments removed, strict package, file splits (2026-10-28)

Branch `work/final-2026-10-27`, commits `693a5119` (Refactor 1) to `1785451a` (Refactor 6), from the local tag
`archive/pre-refactor-2026-10` = `c33eb61e`. Reading guide: `docs/REVIEW-GUIDE.md` on main.

| File | What it shows |
| --- | --- |
| `archive-listing.sha256` | sha256 of `git ls-tree -r` for `docs/evidence runtime/artifacts docs/archive` at `c33eb61e` (line 1) and on `evidence-archive` (line 2): equal, so every archived file is the same blob at the same path |
| `archive-fixtures.txt` | `scripts/check-archive-fixtures.py`: the 15 test fixtures copied off the archive are identical to it |
| `importgraph.py`, `importgraph-after.txt` | AST import reachability from the real entry points; after the refactor only test-only demo helpers, `backend.monitor` (started by Electron through a string the script does not scan in that form) and `strict.qwen2_strict_cuda` (used by the strict probe script that acceptance imports) stay unreached |
| `move_strict.py`, `strict-before.json`, `strict-after.json`, `strict-compare.txt` | the 20 strict modules moved from `heteroes/eval` to `heteroes/strict`: per module, the AST with all imports replaced by `pass` and the concatenated string constants longer than 200 characters (the CUDA sources) hash identically before and after (20/20 SAME) |
| `split_module.py`, `same_defs.py`, `split-worker-cli.txt`, `split-agent.txt` | the worker_cli and agent splits: every top-level definition of the old file has an identical AST in exactly one new file (40/40, 14/14) |

Before the move, the same import graph listed as unreached from every entry point: `heteroes.admission`,
`heteroes.benchmark_stats`, `eval.diagnostics`, `eval.fp16_decoder`, `eval.vllm_weights`, `demo.gsm8k` (and the demo/probe
helpers above); these and their scripts/tests were removed in Refactor 3.

CPU acceptance (`accept.py run cpu`) passed at Refactor 2 (`5ee64ce1`, 2/2) and at Refactor 7 (`f62fc42c`, 2/2); the
runtime suite ran after each other commit (3130 passed). GPU sanity after the strict move: 209 strict tests on the 5070 Ti.

## What this does NOT show

- That the per-file source hashes in engine identity records are unchanged: they change, because import lines changed.
- Equivalence on GPU by itself: the AST proof covers Python and kernel text; GPU behavior is covered by the final
  acceptance receipts in `docs/acceptance/` on main.
- That removed scripts still run: they are gone from main and recoverable only from git history (`c33eb61e`).
- Anything about the deployed lab, which was not touched.
