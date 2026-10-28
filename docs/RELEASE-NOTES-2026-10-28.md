# Release notes — lab release 2026-10-28

From the deployed lab commit `82c37fca` to `main` (accepted source tree `src-18d0b138`, code as of `517a6fb3`; later
commits change only `docs/`). Acceptance: `docs/acceptance/STATUS.md` (25/25 local, 7/7 3060 WSL2, 2/2 3060 native).

## What changes for lab users

- **Strict evaluation (`strict_b22_v1`, ADR-013)**: a Recipe v3 GPU run can evaluate with the strict B22 decoder, which
  gives the same tokens on every supported NVIDIA GPU (measured on SM86 RTX 3060 and SM120 RTX 5070 Ti, Linux, WSL2 and
  native Windows). New Recipe v3 runs created in the lab form default to it; earlier runs keep their recipe unchanged.
- The lab qualifies models per decoder (Models page), sends `evalDtype` only for strict runs, and refuses a strict run whose
  coordinator is CPU-only or shares a physical GPU with one of its workers (one weight set per GPU, D1).
- Run results show audit outcomes (strict first-mismatch, D9); the run form has the stage watchdog fields
  (`hardCapSeconds`, `stallSeconds`, D11); a worker gets one automatic restore recovery per run (D10).
- Recovery points: bounded streaming upload, stateful backoff, verify cache, retention dependency graph (M3).
- SDK: `Lab.qualify(decoder=)`, strict lab runs from the SDK. `strict_int8_lora_v1` (frozen int8 base + FP16 LoRA,
  ADR-014) is standalone/SDK only; the lab refuses it.
- Throughput of the strict engine on the 5070 Ti: 10 119 tokens/s on short32 and 9 941 on chat128 in the final acceptance (about 73% of vLLM); the 80%
  goal was not reached.

## Compatibility

- No lab database schema change between `82c37fca` and this release (no new table or column in `backend/`).
- Run documents of non-strict runs are byte-identical to before (`evalDtype`/`evalChunks` are written only for strict
  runs), so earlier runs resume unchanged.
- Published installers are not rebuilt by this release (r10 desktop installers stay published).

## Known limits

- A strict lab run needs two GPUs (the coordinator cannot share a GPU with a worker).
- M3.bookkeeping stays OPEN: the managed product runner's per-generation bookkeeping growth (1.7 s to 11 s over 600
  generations, measured earlier) is not re-measured; the standalone strict soak stays flat (gate M5.long-run).
- Two strict workers in one process on one GPU fail during CUDA graph capture; the lab never starts that layout.

## Rollback

1. `python3 -I ~/.local/share/heteroes-lab/app/scripts/local-lab.py stop`
2. `git -C ~/.local/share/heteroes-lab/app checkout --detach 82c37fca` and rebuild its web UI
   (`npm run build --workspace frontend -- --outDir ~/.local/share/heteroes-lab/app/frontend/dist`).
3. `python3 -I ~/.local/share/heteroes-lab/app/scripts/local-lab.py start`, then `scripts/verify-public-lab.py`.

Roll back only while no strict run is active (the old code does not know `strict_b22_v1`). Rehearsal: a database written
by this release was reopened and changed by `82c37fca` and reopened again by this release, with the same devices and
experiments in every phase (evidence `docs/evidence/2026-10-28-release-rollback` on the branch `evidence-archive`).
