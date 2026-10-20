# Python rewards on the web lab (2026-10-20)

Owner decision (ADR-008 "Owner answers (2026-10-20)"): a researcher's Python scorer and Python coefficient rule are
fully open on the web lab. The web form uploads a `.py` file and a function name; the lab computes the file's
SHA-256 (the same identity `heteroes run` gives a local file), completes the scorer spec or the `python@1:<sha>` rule,
checks that the plan pins exactly the uploaded files, freezes them with the experiment and audits
`PYTHON_CODE_FROZEN`. The COORDINATE command carries the code; START_WORKER does not, and a worker refuses a
configuration with code. The coordinator writes each file into the run folder, re-checks its hash and runs it in a child
process with a time limit and without `HETEROES_*` credentials (`heteroes.v3.sandbox`). The validation tracker uses the
same scorer.

Checks: `runtime/tests/v3/test_v3_python_rewards.py` (hash identity, pinning rules, worker refusal, child process:
results, numpy results, prints kept off the reply channel, exception, crash, time limit, restart, credentials),
`backend/tests/test_v3_study.py::test_v3_python_code_is_frozen_and_reaches_only_the_coordinator`. Mutation: runtime
8/8, backend 4/4. Full suites: runtime 2401 passed, backend 354 passed; web types, i18n and units pass.

## What this does NOT show

- No GPU run with a Python reward through the lab yet. On the CPU, a real managed runner and worker process run a
  Python reward and a Python coefficient rule end to end (`runtime/tests/v3/test_v3_product.py::
  test_managed_run_with_a_file_backed_dataset_and_a_python_reward_and_rule`, added with the large-dataset commit).
- The child process is not a security boundary: the code has the coordinator user's permissions (accepted risk in
  `docs/SECURITY-NOTES.md`). There is no memory or file-system limit.
- The coordinator device's own page does not yet show which experiment's code it runs; the experiment and the audit
  log do.
