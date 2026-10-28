# Human-review continuation (2026-10-24)

Starting point: clean `fix/human-review-single-model-2026-10-24` at `ecc2d19`.
The owner renewed autonomous implementation, GPU and SSH authorization, and requested an SGLang comparison.
No push, merge, deployment, device approval/contribution changes or learning run.

## Scoring reservation

The initial ten mutants target commit `1cf0843`: committed-text digest comparison, duplicate leader/waiter,
error propagation/notification, owner/chunk checks, and both request/audit locks. The first invocation was
interrupted to add a finite subprocess timeout; `scorer-mutation-01.log` is not a completed check.
`scorer-mutation-02.log` is exploratory: the new publication regression test was added while it ran, so its
control and later mutants do not use identical tests. Do not use it as the final mutation acceptance.

Code review found a reservation gap: the leader removed its flight after scoring but before canonical commit.
A new arrival could start a second scorer in that interval. `scorer-publication-red-01.log` reproduces this;
`scorer-publication-green-01.log` passes after retaining the reservation through commit. Unexpected scorer
exceptions also wake existing waiters; they cannot commit a missing reward.

`scorer-mutation-03.log` is the complete rerun: control **9 passed**, **11/11 mutants killed**, including
releasing the reservation before commit. The scoring-lock mutant hits the explicit 45-second subprocess cap;
the other mutants fail assertions. Mutations run on disposable source/test copies, with CUDA disabled.
Manifests: `scorer-mutants-01.json`, `scorer-mutants-02.json`.

Reproduce from the repository root:

```bash
python3 -u scripts/mutation-check.py --repo runtime --copy src --copy tests/ledger \
  --env CUDA_VISIBLE_DEVICES= --env PYTHONPATH=src:tests/ledger \
  --test 'timeout 45s /home/pc5070ti/miniforge3/envs/heteroes-match/bin/python -m pytest -q tests/ledger/test_worker_api_concurrency.py' \
  --mutants docs/evidence/2026-10-24-human-review-resume/scorer-mutants-02.json
```

## What this does NOT show

No exactly-once scorer effects across process crashes, bounded usage delivery, durable worker outbox,
watchdog/recovery acceptance, or completion of M2–M6. These tests exercise coordinator concurrency on CPU.
SGLang probe unit receipts in this folder test evidence comparison and GPU opt-in only; hardware results
belong in `../2026-10-24-sglang-probe/`.
