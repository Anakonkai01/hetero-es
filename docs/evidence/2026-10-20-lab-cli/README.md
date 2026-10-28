# CLI experiment offered through a managed lab (2026-10-20)

`heteroes serve --lab` reuses the installed headless Worker's pairing, qualification, agent, boot-scoped OFF/ON and drain
protocol. It waits for approval in the requested workspace, registers/uploads pinned model and dataset files through the
existing routes, freezes Python code and submits a managed experiment. It never approves or turns contribution ON.
`lab-offer.json` binds the input identities and remote IDs; changed local files cannot silently reuse a frozen asset.

## Receipts

- `before.log`: three failures before implementation. `first.log`: a regression test caught the built-in model row's
  absent ID matching an absent saved model ID; fixed by requiring a saved ID before matching it.
- `second.log`: all three route tests pass. `early-validation-before.log` and `terminal-before.log` record additional
  tests before adding early unsupported-choice validation and exit for an already completed offered experiment.
- `backend-final.log`: 9 passed, including CPU admission tests. The real backend routes receive streamed model/data uploads,
  publish them, freeze the Python source, validate the selected coordinator/workers and accept submission. Repeat calls
  reuse the same experiment. No Torch or NumPy is imported in these backend tests.
- `agent-final.log`: 5 passed. Agent boundary tests enforce the chosen workspace, private token handoff, explicit owner ON,
  safe quit, missing user-token refusal and retry of a completed offer. The Bridge is a fixture in these boundary tests.
- `mutation-backend.log`: 3/3 mutants killed (input identity, coordinator choice, sampler). `mutation-runtime.log`: 4/4
  killed (missing access token, wrong workspace approval, automatic ON, waiting on a completed experiment).

## What this does NOT show

- These are real API/storage route tests and fixture agent-boundary checks, not a new GPU run through the packaged lab.
- No user/device approval, contribution change, live deployment or public release is authorized by this receipt.
- Model qualification still belongs to each selected GPU. The CPU coordinator skips text qualification, not pinned files.
- Retry preserves completed asset/experiment IDs; an interrupted signed upload may leave a temporary upload object on the
  lab until its normal cleanup. The installed CLI and the matching r11 lab are prerequisites.
