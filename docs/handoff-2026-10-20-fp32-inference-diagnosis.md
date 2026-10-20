# R11 continuation: audit mismatch localized to FP32 inference

This supersedes the diagnosis status in [the audit-stop handoff](handoff-2026-10-20-audit-mismatch-stop.md).
The owner subsequently authorized full continuation. Release step 5 is still incomplete; main remains
086c282 and installed candidate5/live r10 remain unchanged. No product source or frozen numerics changed.

## Established cause of this candidate's mismatch

[Original investigation](evidence/2026-10-20-audit-mismatch-investigation/RESULTS.md): both GPUs independently
reconstructed all ten original updates, checking each intermediate child hash. On exact g10/c5, input IDs,
attention masks, perturbed FP16 and shadow FP32 weights match bit for bit. Two repeats on each GPU reproduce
its original completion hash. Row 0 first diverges at generated token 13: 5070 selects 16861, Quang selects
4995. Top-two FP32 score differences change the greedy winner. This exact offline reproduction localizes
the failure to inference arithmetic/decoding, rather than audit traffic or different candidate weights.

Eager attention aligns this one case, but does not eliminate score differences. Forced math SDPA and
ordinary model.double() still disagree. Full-reference FP64 agrees only after preserving FP64 through
the model's internal explicit FP32 conversions. This is diagnostic, not a product fix or a theorem.

## Owner's practical constraint and measured alternative

The owner replied: "nhưng trong thực tế máy gpu consummer làm gì xài fp64". This is NOT approval of the
earlier proposed full-FP64 decoder. GPU generation should remain FP32 pending a policy decision.

[Selective CPU probe](evidence/2026-10-20-fp32-margin-cpu-probe/RESULTS.md): only 2/256 token slots have
top-two gaps below 0.01. A scratch-only final logits processor keeps GPU inference FP32 and recomputes
those prefixes with a CPU FP64 reference. Both full token arrays/texts then match the original 5070 hash.
Measured guarded generation is 1.182 s on 5070 / 2.331 s on Quang, including lazy reference creation;
single ordered samples, not a benchmark. The reference parameter copy alone costs ~3.95 GB RAM for 0.5B.
Two focused helper tests pass, all four mutations killed; test-before-implementation failure preserved.

The empirical gate is not a numerical error bound and could itself disagree at its threshold. The result
does not justify a universal bitwise claim or general large-model deployment. No stock decoder meaning
was changed. Numerical-contract section 17 leaves near-tie policy to the owner. An asynchronous question
is pending: approve implementing a separate FP32 + CPU-reference decoder for further validation, or
require no FP64 even on CPU and investigate another design. Do not infer approval from time or "full".

## Owner decision after these receipts

The owner explicitly selected "Triển khai decoder FP32 + CPU dự phòng, kiểm chứng tiếp".
A separately identified decoder is now authorized for implementation and further validation. This
does not approve any release claim or waive the fresh candidate, hardware, long-run and flag-day gates.
The earlier pending-question wording above records the state when the probe was captured.

## Operational state and reproducibility

- All probe processes have exited; no managed run was resumed. Four devices remain OFF/unallocated as
  recorded in the previous handoff. Isolated server and desktop Workers remain idle; CLI agents stopped.
- SSH keys work, memory is readable. No credentials were printed/copied. Public lab unchanged.
- Local scratch: `.scratch/r11-audit-investigation/`; Quang: `/tmp/heteroes-audit-investigation/`.
  Cache `parent-fp16.bin` is private scratch (~1 GB) and SHA256-verified before reuse. Original ten-update
  replay scripts/receipts are preserved, so cache is not the sole reconstruction proof.
- **Correction to previous handoff:** `.scratch/r11-long-run2/private-run-copy/` did NOT contain dataset/
  splits. These were recovered from Quang's verified worker cache into investigation inputs/evidence.
- **Correction/retention detail:** runtime retention pruned the original g10 parent weight file on Thao.
  No operator cleanup occurred. Independent ten-update reconstruction recovered and verified that parent.
- Use packaged `heteroes.product.remote.worker_environment()` for Quang probes, with pinned source path;
  setting only `/usr/lib/wsl/lib` can select a stale Linux PTX JIT library and segfault. The first probe's
  launch mistake is documented; successful receipts use the helper. No driver/runtime was modified.

## Resume

Resolve the pending numerical-policy choice, then tests/mutation checks before any production behavior.
A new decoder requires its own recipe identity and declared policy; preserve hf_generate and historical
hashes. Validate supported configs, errors, CPU/memory limits and both device implementations. Do not
loosen audit equality or turn infrastructure failures into rewards to pass acceptance.

Any behavior fix requires full checks, new candidate packages and renewed Windows/WSL/Linux acceptance.
Then a fresh predeclared step 5: 50 generations, three GPUs, real audits, planned Quang outage around
generation 20 and ~5-minute return, retry proof, full independent candidate/context/update/child parity.
Windows quit/relaunch/uninstall, FF merge/push, flag day and final documentation consolidation remain.
Each irreversible flag-day operation still requires explicit chat "đồng ý". No release readiness is claimed.
