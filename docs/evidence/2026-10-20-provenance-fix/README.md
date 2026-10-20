# Provenance fix: a packaged copy no longer reports an enclosing checkout's commit (2026-10-20)

`runtime_info.code_info()` ran `git rev-parse HEAD` from `REPO_ROOT = parents[2]`. Git walks up to any enclosing
repository, so the packaged run under `.scratch/` recorded the root branch's commit as if it were the code that ran.

Fix: git is believed only if `runtime_info.py` itself is tracked by the repository git finds
(`git ls-files --error-unmatch -- <this file>`); otherwise both fields are `None`. Packaged runs keep identifying their
exact bytes through `sourceTreeSha256` (`product/recovery.py:source_identity`), which is unchanged.

Tests (`runtime/tests/test_runtime_info.py`): a copy inside a temporary git repository that tracks a sibling file but
not the copy reports `None`/`None`; the same copy committed reports the repository's `HEAD` and `git_dirty: False`.
`mutation-check.txt`: 3 of 3 mutants of `mutants.json` killed (no guard, inverted guard, guard on the directory
instead of the file).

## What this does NOT show

- Observations already recorded with the wrong `git_commit` (for example the two-machine run `6590307f…` driven from
  `.scratch/`) are not rewritten; read their `sourceTreeSha256` instead.
- It was not run inside a packaged Windows or Linux app; the check is a temporary repository on Linux only.
- A copy that is deliberately committed into another repository will still report that repository's commit, which is
  then the honest answer.
