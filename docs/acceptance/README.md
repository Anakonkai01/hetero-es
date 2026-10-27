# Acceptance

`scripts/accept.py` runs the checks of milestones M0–M6 and reports each gate. The rules live in
[acceptance/core.py](../../acceptance/core.py); the checks and gates in [acceptance/registry.py](../../acceptance/registry.py).
[STATUS.md](STATUS.md) is generated from the committed receipts in `receipts/`; do not edit it by hand.

## Gate states

| State | Meaning |
| --- | --- |
| PASS | Every check the gate names passed on this source tree (all tracked files outside `docs/`). |
| FAIL | At least one of its checks failed. |
| NOT_RUN | Some of its checks have no result for this source tree yet. A missing result is never a pass. |
| DEFERRED | It cannot be checked with the available hardware or conditions; the reason is printed. |
| OPEN | The work it needs is not done; what is missing is printed. |

A receipt from a dirty working tree is kept but never makes a gate pass. Receipts of different hosts are merged
only for the same source tree. Documentation changes do not change the source tree.

## Commands

```bash
scripts/accept.py list
scripts/accept.py run cpu --keep                                  # check-all + acceptance self-tests, here
HETEROES_GPU_ACCEPTANCE=1 scripts/accept.py run gpu perf --keep   # GPU suite, trained parity, throughput floor
HETEROES_GPU_ACCEPTANCE=1 scripts/accept.py run mutation --keep
scripts/accept.py run package --keep                              # Linux packages carry the exact runtime bytes
scripts/accept.py remote 3060-wsl gpu --keep                      # stage HEAD on Thảo's 3060 (WSL2), run, fetch
scripts/accept.py remote 3060-native gpu --keep                   # the same 3060 under native Windows
scripts/accept.py report --write                                  # regenerate STATUS.md
```

`remote` stages `git archive HEAD` of the runtime and the acceptance system, so commit first. It needs SSH to
Thảo's machine with the controller's own keys; no credentials are stored in this repository.

## Pinned references

- `acceptance/golden/strict-b22.json`: trained Qwen/Smol/Tiny parent, canonical ± and restore hashes of runtime
  `0eb86cb9`, equal on the 5070 Ti, 3060 WSL2 and (Qwen) native Windows. Built by `make_strict_golden.py` from the
  sealed receipts of `docs/evidence/2026-10-27-strict-combined-acceptance`.
- `acceptance/golden/throughput.json`: token hashes of the matched short32/chat128 workloads and a throughput floor
  per GPU, 0.98 × the selected runtime's ABAB mean on that GPU.
- `acceptance/mutants/*.json`: mutation groups; every mutant must be killed.

## What this does NOT show

A PASS is the stated checks on the stated hosts and source tree. It is not a proof for every input, model,
GPU architecture or operating system, and it is not a learning result.
