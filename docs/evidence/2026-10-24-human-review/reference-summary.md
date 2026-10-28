# Experimental reference and restored hardware access

Scope: ADR-012 arithmetic/graph reference, standalone probes only. Source contract:
[strict-reference-v1.md](../../../runtime/docs/strict-reference-v1.md).
The permission profile was updated after the earlier socket/device failures. `hardware-access-02.json` records that
earlier restriction; `hardware-access-03.json` records successful key SSH/GPU access. No sudo, driver installation,
deployment, service restart or device approval change was needed.

## Observations

The portable operator/tiny-Qwen probe agrees **bit-for-bit** across CPU, RTX 5070 Ti and both RTX 3060 hosts in WSL2.
The compared object includes source/config fingerprint, schema, parent and perturbed weight hashes, seven operator
output hashes, four graph cases (two parent/two perturbed), last-position logits, generated token IDs, rewards and
exact restore. Identical published inputs use integer/power-of-two fixture values rather than a device RNG initializer.
The CPU/GPU reference tests are separate from the CPU-only HF oracle used in the unit tests.

The real pinned Qwen2.5-0.5B reference also completes on all four targets. Model-files hash, backend identity,
schema, parent before/after hash, prompt IDs, seed 7001, sigma 0.001, generated token `[17607]`, text and reward agree.
Every restore succeeds. This is **one prompt, one candidate and one new token** per target, not a rollout corpus.
The expected answer is 4, but the truncated completion is ` ?\n`, so the measured last-integer reward is zero.
This is a lifecycle/numerics probe, not a quality or learning result.

| Target | Full-model rollout host wall seconds | Peak allocated CUDA bytes | Peak reserved CUDA bytes |
| --- | ---: | ---: | ---: |
| CPU | 49.414 | n/a | n/a |
| RTX 5070 Ti | 46.325 | 1,076,176,896 | 1,203,765,248 |
| RTX 3060 Quang, WSL2 | 144.651 | 1,076,176,896 | 1,203,765,248 |
| RTX 3060 Thao, WSL2 | 148.679 | 1,076,176,896 | 1,203,765,248 |

Live FP16 model/buffer storage plus the reference's RoPE constants is 988,065,920 bytes on each target; the permitted
CPU parent snapshot occupies 988,065,536 bytes. This counts backing storage for this probe's sole inference role;
CUDA allocator peaks are reported separately. It is not an inventory of every process on a physical GPU.
The eager reference's Python loops and synchronization overhead make it unsuitable for promotion. Optimizing the
specified sequence is the next gate; a default change would be premature.

The native FP16 lifecycle baseline (`qwen-5070ti-native-01.json`) also restores exactly without a shadow. Its four-token
rollout took 2.286 seconds in this single cold probe. That measurement is neither a strict inference qualification
nor a controlled speed ratio against the one-token reference runs.

## Verification and intermediate failures

- `reference-comparison-01.json` independently checks the finite cross-machine comparisons and hashes its input receipts.
- `reference-eval-regression-01.log`: 283 CPU tests passed, 13 hardware-dependent tests skipped.
- `reference-validation-red-01.log`: the added masked-invalid-token test failed before the validation fix.
- `reference-probe-red-01.log`, `hardware-probe-red-01.log`: probes were tested before their new CLI behavior existed.
- `reference-mutation-01.log`: 13/14 targeted defects detected. The first memory guard observed `_to_copy` only;
  this PyTorch version dispatches `.float()` through `aten::to`, so full-matrix widening survived.
- `reference-mutation-02.log`: after covering both cast dispatches, all 14/14 targeted defects are detected, including
  full weight widening. Other defects exercise reduction pairing/tails, FTZ, bias, masks, RMS epsilon, RoPE, causal
  attention, cached keys, MLP gating, ties, repetition penalty and invalid input tokens. The first receipt is retained.
- `reference-probe-mutation-01.log`: control 10 passed; all 5/5 probe defects detected, including missing GPU
  opt-ins, skipped perturb/restore and ignoring the selected backend.
- `checks-reference-01/`: full CPU integration checks, including 2,725 runtime tests and 439 backend tests, source
  packages, UI units, type/lint/i18n/build and fixture browser/Electron checks. The sole failure was an old browser
  selector reading a device label together with its newly displayed GPU detail. The check now asserts both fields
  separately. `web-live-retry-01/` passes that browser contract on a fresh fixture lab. The failed original remains;
  `checks-reference-overview-01.json` records the targeted rerun rather than relabeling the original suite as green.

Quang initially segfaulted in the system `libnvidia-ptxjitcompiler.so.580.178.04` during CUDA discovery while the
Windows driver was 617.42. A process-local `LD_LIBRARY_PATH` selected the matching Windows-provided JIT library from
the WSL driver directory; both probes then succeeded. This is consistent with
[NVIDIA's WSL driver guidance](https://docs.nvidia.com/cuda/wsl-user-guide/). No global driver configuration was edited.
Remote source/receipts remain isolated in `/tmp/heteroes-review-20261024-01`; existing models/runtimes were read only.

## What this does NOT show

- Universal strict inference, supported native Windows, or acceptance across a broad prompt/candidate/context corpus.
- A separate perturbed-weight hash for the full 0.5B probe; that stronger check exists for the tiny fixture only.
- A performant generated kernel, end-to-end ES run, cross-process ownership of one model, validation/export lifecycle,
  admission/cache identity integration, production packaging, recovery/audit fixes or quantized-base/LoRA acceptance.
- Completion of M1 or authorization to replace the managed backend, deploy, change device state or start a learning run.
