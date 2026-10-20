# On-demand model qualification (2026-10-20)

Tests and mutation controls for establishing a lab reference on the first device and reproducing it on another device.

## What this does NOT show

- Tiny CPU-model checks establish the mechanism, not real GPU or cross-platform compatibility.
- The dynamic reference probes full-model signed perturbation, repeated texts/rewards and exact restoration. It does
  not certify all workloads, decoding settings, custom LoRA target sets or near ties.
- Model registration and qualification do not establish learning benefit.

The continuation now includes workspace model-check routes, typed agent commands, a trusted subprocess and web controls.
The first device establishes a frozen reference; later devices receive it verbatim. The CPU lab independently validates
both signed repeats, pinned inputs and restoration, binds qualification to the current native self-test hash, and
keeps a physical GPU reservation until process death is explicitly confirmed. Restore failures quarantine the device.
Native desktop self-test documents remain unchanged; dynamic qualifications are applied separately for scheduling.
Device credentials travel only through the child environment, never command arguments or the persisted input file.

Validation:
- Backend targeted controls: 14 passed; 5/5 deliberate mutations detected. Full backend suite: 348 passed.
- Runtime product/transfer checks: 23 passed; agent/child/transfer mutation controls: 13 passed, 5/5 detected.
- Additional agent/reference regression: 73 passed. Tiny-model probes run on CPU in a separate process.
- `web-after/browser/` records starting and cancelling through the real browser/API on a disposable CPU lab.
- The initial `web-before/` build failed due to a harness path, corrected in `web-before-v2/`; that probe then failed as
  expected because the old page had no model-check controls. These are not hardware failures.
- `model-transfer-tests.log` includes three managed-subprocess failures from invoking the tests at the repository root;
  those tests require the `runtime/` working directory. `runtime-product-final.log` reruns them correctly and passes.
- The two explicitly ignored raw failing backend logs contain synthetic session tokens. Their public `.redacted.log`
  copies remove the bearer values; raw local receipts are preserved and excluded from version control.

The packaged/GPU model-check journey is still pending. The concurrently running GSM8K comparison uses the earlier
unmodified `637fce3` Worker package, not these new model-check sources.
