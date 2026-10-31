# Plan (later session): the researcher SDK submits to the shared lab, and the notebook shows a researcher using it

Owner, 2026-10-22 ~12:30, after the midterm notebook: "tại sao cái notebook ko thể hiện được nhà thí nghiệm có thể sử dụng
hệ thống như thế nào… mấy cái sdk gì gì đó ko được sử dụng hả". Decision: **planned for a later session, not now** (the
midterm demo today keeps the current notebook). Not started.

## The gap (as of `26c6d89`)

- `heteroes.sdk` (`runtime/src/heteroes/sdk.py`: `ESConfig`, `@reward`, `ESTrainer`) runs **on one machine only**:
  `ESTrainer.train()` calls `heteroes.v3.local.run_local`; its docstring says "nothing is sent anywhere".
- The shared lab is reached another way: a recipe JSON → `heteroes.v3.lab_cli.offer_experiment(spec, coordinator,
  workers, api, directory)`, which uploads the model, the dataset splits and any Python scorer/coefficient code, and
  creates the experiment (idempotent through `lab-offer.json`). The GSM8K notebook calls it through
  `heteroes.demo.lab.DemoLab.offer` / `gsm8k.launch(lab, tier)`, so a reader never sees the recipe, the reward or the
  submit; since the midterm edition the tier cells only `load(...)` saved records.
- So there is no `ESTrainer(...).submit(lab)`: a researcher either runs the SDK alone, writes JSON and calls an
  internal function, or uses the web page.

## Wanted

1. **SDK → lab bridge** (code + tests + mutation check): `ESTrainer.submit(lab, coordinator, workers, directory)` built on
   `config()` / `to_config()` and `offer_experiment`; a `Lab` (session from `scripts/lab-login.py` or a token) with
   `devices()`; a returned run object with `.status()`, `.watch()` (the live dashboard), `.results()` (validation,
   selected checkpoint, test score, per-device work and audits **from the ledger**, since the lab timeline of a long run
   is partial: RESULTS.md finding 10). A Python `@reward` must travel as pinned code exactly as `offer_experiment` already
   does for `kind: python`.
2. **Notebook opening section "You are the researcher"**: sign in, list the devices, write the GSM8K reward in Python
   with `@reward`, declare `ESConfig`, `submit`, `watch`, `results`. The tier 1-3 sections stay as the evidence part.
3. **A real short run through that path** on the lab's devices (they are busy with tier 3 until ~2026-10-23 11:00; a
   submit before then only queues). Optionally a tiny `ESTrainer.train()` on one machine in the notebook.

## Open questions for the owner (grill before planning)

Name and shape of the API (`submit` on `ESTrainer` or a separate `Lab.submit(config)`); whether `watch()` blocks;
which result fields a researcher expects; whether a declarative scorer stays the default for shared labs.
