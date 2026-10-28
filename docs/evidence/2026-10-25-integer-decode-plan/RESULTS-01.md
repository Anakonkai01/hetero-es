# Selected bounded decode scheduling: source 97f62431

- CPU check-all: **3038 passed / 297 skipped**, backend **452 passed**, complete check-all **ALL PASS**.
- Selected operator/reference/decoder/CLI suite: **378 passed on each of four GPUs** (two5070Ti, two3060WSL2).
- Native Windows11/3060: **378 passed** in the existing isolated pinned environment, source manifest183 files
  unchanged before/after. Four pinned layouts, both precisions, parent/changed/restored portable identity,
  prefill/captured logits, cache, token and weight hashes match Linux5070Ti exactly;46 compiled audits available,
  zero PTX/SASS violations. See `native-windows-comparison-01.json`.
- Planner mutation check: **5/5 killed** after a passing control, including duplicate workspace undercount,
  capacity-only accounting and ignoring the workspace cap.
- Linux Worker/Server packaging check passes. Worker source and embedded Server SDK wheel contain the exact nine
  selected runtime source files, including integer_plan; frozen v1 paths have no changes since033065d.
- Trained local B22 B1/B8/B32 (total output token/s): Smol262.3/1206.4/2863.3;
  Tiny180.0/691.6/1377.3; Qwen263.0/1170.4/2810.7. Parent/canonical7001±/restore prefill/token/text/reward
  matches the preceding eeb74c23 source; exact parent restore. See `trained-comparison-01.json`.

## What this does NOT show

No managed/default activation, universal hardware or general quality theorem, trained current-source cross-device
completion, native installer acceptance, end-to-end ES speed, near-vLLM attainment or completion of M0–M6.
Native tests are source/fixtures, not a full trained acceptance. No push/merge/deploy, device-state change or learning.
