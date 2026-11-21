# Acceptance

`scripts/accept.py` runs the checks of milestones M0–M6 and reports each gate. The rules live in
[acceptance/core.py](../../acceptance/core.py); the checks and gates in [acceptance/registry.py](../../acceptance/registry.py).
Reports are generated from the committed `receipts/` for a single source identity.

| Report | Source |
| --- | --- |
| [STATUS.md](STATUS.md) | B-021, `src-c9f8f9d8…`. This is the latest tree with the full 37-pair matrix. Upstream `main` (`38327051`) has the same source identity. |
| [STATUS-src-89176a3d.md](STATUS-src-89176a3d.md) | B-022. The focused backend regression has a separate record in [FINDINGS-B](../review/FINDINGS-B.md#b-022--a-periodic-recovery-point-verified-after-the-final-point-replaces-it-in-the-run-projection-p3). |
| [STATUS-src-6c669c56.md](STATUS-src-6c669c56.md) | Historical source snapshot. |

## Gate states

| State    | Meaning                                                                                                                     |
| -------- | --------------------------------------------------------------------------------------------------------------------------- |
| PASS     | Every check the gate names passed on this source tree (tracked files excluding `docs/`, `runtime/docs/` and root Markdown). |
| FAIL     | At least one of its checks failed.                                                                                          |
| NOT_RUN  | Some of its checks have no result for this source tree yet. A missing result is never a pass.                               |
| DEFERRED | It cannot be checked with the available hardware or conditions; the reason is printed.                                      |
| OPEN     | The work it needs is not done; what is missing is printed.                                                                  |

A receipt from a dirty working tree is kept but never makes a gate pass. Receipts of different hosts are merged
only for the same source tree. The source hash excludes `docs/`, `runtime/docs/` and root Markdown. Markdown elsewhere
is included by the existing hash rule.

## Commands

```bash
scripts/accept.py list
export ACCEPT_PYTHON="$HOME/miniforge3/envs/heteroes-match/bin/python"
scripts/accept.py run cpu --keep                                  # check-all + acceptance self-tests, here
HETEROES_GPU_ACCEPTANCE=1 scripts/accept.py run gpu perf --keep   # GPU suite, trained parity, throughput floor
HETEROES_GPU_ACCEPTANCE=1 scripts/accept.py run faults --keep    # two GPUs, including CPU replay of every update
HETEROES_GPU_ACCEPTANCE=1 scripts/accept.py run mutation --keep
scripts/accept.py run package --keep                              # Linux packages carry the exact runtime bytes
scripts/accept.py remote 3060-wsl gpu --keep                      # stage HEAD on Thảo's 3060 (WSL2), run, fetch
scripts/accept.py remote 3060-native gpu --keep                   # the same 3060 under native Windows
scripts/accept.py report                                         # render the report for HEAD
```

Use `scripts/accept.py report --tree <full-source-id>` to render a specific source. The `--write` flag replaces
`STATUS.md`, which tracks the latest fully accepted tree. For a review branch, save the rendered report under its
source ID and keep the accepted report available.

`ACCEPT_PYTHON` selects the controller interpreter for self-tests, mutation orchestration and fault probes. The fault
probes import PyTorch when replaying updates on CPU, so use the runtime environment above. `check-all.sh` independently
uses `.venv-backend/bin/python` for backend tests and the runtime environment for numerical tests. Remote runs select
their configured runtime interpreter automatically.

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
