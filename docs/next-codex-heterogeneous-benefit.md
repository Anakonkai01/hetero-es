# For Codex: why extra GPUs help so little, and what to dig into

Written 2026-10-23 by Claude at the owner's request. Goal: find out where generation time goes on mixed GPUs and make a
second/third (slower) machine pay off, **without** breaking bit-exact parity. Numbers below are measured; the causes
are hypotheses until you profile them.

## What is measured

Sources: `docs/evidence/2026-10-23-overnight/README.md` (sections 1, 3, 5), `speed-gpu/m{1,2,3}/timeline.json`,
soak run events `~/.local/share/heteroes-worker/agent-state/runs/44e65d7b2975447fa15fe85f115bad92/events.jsonl`.

Short run, 48 antithetic candidates, Qwen 0.5B, GPU engine v2 (`speed-gpu/`, one sample per cell):

| machines | wait per gen (s) | per worker: candidates, busy s, first job after open |
| --- | --- | --- |
| 1 (nhan 5070 Ti) | 23.6-27.4 | 48, 17.3-18.1 s busy, starts at +2.4 s |
| 2 (+ nhut 5070 Ti) | 14.0-14.4 | ~28 / ~20, ~9-10 s busy each, +2.4 s |
| 3 (+ thao 3060, Windows) | 13.6-17.3 | 5070 Tis ~23 / ~20; 3060 only 3-6 candidates at 1.1-2.1 s each, starts at +6.8-8.4 s |

- One candidate costs ~0.35 s on a 5070 Ti and 1.1-2.1 s on the 3060: work units are tiny, so fixed costs dominate.
- Every worker idles ~2.4 s at the start of a generation (replaying the update before its first job); the 3060 ~7-8 s.
- Adding the 3060 did not lower `wait`; the 5070 Tis show more idle gaps (3.5-6.6 s vs 0.6-1.6 s with two machines),
  consistent with the slow machine holding the last candidates (tail).
- The coordinator update (~2.3 s) runs after `wait` while all workers idle.
- Older two-machine scaling (2026-10-09): 1.29-1.33x, near that pair's ceiling (`runtime/docs/report/CLAIMS_AUDIT.md`).

Soak, 24 candidates/gen, 600 generations: nhan 7,696 attempts, nhut 6,294, Windows 3060 **410**. Phase medians from
`events.jsonl` (seconds):

| generations | open→complete (candidates) | complete→published (update) | published→generation_done | generation_done→recovery point | open→next open |
| --- | --- | --- | --- | --- | --- |
| 5-50 | 9.7 | 2.8 | 0.8 | 0.9 | 18.6 |
| 300-350 | 8.1 | 3.3 | 3.6 | 7.1 | 23.4 |
| 550-598 | 7.7 | 3.8 | 3.3 | 8.0 | 24.4 |

**Candidate work is only ~1/3 of a late generation; the two bookkeeping steps grow with run length, from 1.7 s to
11.3 s.** This is the first thing to fix: it is the same for any number of machines.

## Hypotheses, in the order to check

1. **Per-generation work that grows with the run** (biggest and cheapest win):
   - `coordinator.py` ~575-588: `audit_counts()`, the `audit JOIN candidate … WHERE generation=?` count and
     `usage.summary(...)` run every generation. Check for full scans or missing indexes (`EXPLAIN QUERY PLAN`).
   - `product/recovery.py capture_point` + `v3/recovery.py capture_state` run **inside the generation barrier**: SQLite
     backup of the whole ledger and `usage.sqlite`, SHA-256 of the selected weights (~1 GB) and dataset files,
     `source_identity` hashing the runtime sources, every generation (backup policy default `interval: 1`).
   - Page-cache churn from the upload thread (`product/cloud_sync.py`, see `docs/evidence/2026-10-23-oomd-review/`).
2. **Fixed start cost per generation**: every worker replays the update before its first candidate (~2.4 s on a 5070
   Ti, ~7 s on the Windows 3060). Look at overlapping it with the coordinator's own update.
3. **Tail effect from the slow machine**: default scheduler is `Greedy` (`dispatch.py`; chosen in
   `product/runner.py scheduling`, `schedulerPolicy` defaults to `"greedy"`). `GreedyTail` exists but earlier tests
   (2026-10-09) showed no difference on 5070 Ti + 3060. Re-test with the per-worker speeds now known.
4. **Work units too small**: at 0.35 s per candidate, lease/report round trips and start-up are a big share. Measure
   batching several candidates per lease (or bigger chunks for fast workers), and longer evaluations (more prompts or
   tokens) where a slower GPU can contribute.
5. **When a slow machine is simply not worth it**: the admission tool (`admission.py`) predicts the gain of a worker
   but is not in the automatic join flow. A proper result could be "the system tells you the 3060 adds < X %".

## Constraints

- Numerical contract (`runtime/docs/numerical-contract.md`): every change must keep the same weights hash chain for
  1/2/3 machines and CPU/GPU noise. Re-run the six-cell comparison in the overnight README (section 3) as the check.
- Changes inside `es/` or `noise/` need the owner's approval first. Scheduling, bookkeeping, recovery and I/O do not.
- System claim only: no learning claims. Report speed with ≥ 3 repeats per cell and confidence intervals.
- Coordinate with the oomd/backup fixes in `docs/operations-decisions-2026-10-23.md`; they touch the same code.

## Deliverables

1. A per-generation time breakdown (profiling, not only events) for 1, 2, 3 machines and for early/late generations.
2. Fix of the growing bookkeeping cost, with a 600-generation check that `open→next open` stays flat.
3. A measured answer for the slow GPU: speedup with and without it after fixes 1-2, and whether the scheduler or the
   admission should leave it out.
