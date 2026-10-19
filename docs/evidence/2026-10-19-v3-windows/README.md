# Native Windows v3 runtime probes and r11 resolver inputs — 2026-10-19

Owner selected Windows on thaonguyen's RTX 3060. Protocol:
`docs/v3-windows-qualification-2026-10-19.md`, probe helpers commit `69534ec`.
Numerical runtime source extracted at `0bbf881`, matching the paired Linux/WSL
qualification; the probe normalizes source path separators before comparison.

## Actual result, including the failed boundary

All three native Windows cells independently finish 8 candidates, 8 matching audits
and exact independent CPU replay of both GPU updates. Full has 2 non-noop updates;
subset/LoRA have none. Native CPython 3.12.15, Torch 2.13.0+cu132, Transformers
5.17.0, NumPy 2.5.3 and isolated PEFT 0.21.2.

- `compare-full.json`: **PASS**, all 32 texts, rewards, recipe/plan/source hashes
  and child hashes match the 5070 Ti baseline.
- `compare-subset.json`: **PASS**, same 32-text comparison.
- `compare-lora.log`: **FAIL at recipeHash**, not native Windows LoRA portability
  acceptance. `lora-recipe-diff.json` shows the recipe difference is the initial
  adapter SHA-256. Both sides generated adapters independently from seed 7; the
  initial bytes differ across OS despite the same declared software versions.
  The cause below that boundary is not established. Do not change numerical
  contracts or silently rerun this result as a pass.

The product already pins and transfers the coordinator's initial adapter. A useful
NEXT test is a native Windows worker consuming the exact Linux adapter through
that existing path. That is an inference about how to qualify the supported
worker role, not a result shown here. Native Windows coordinator is not supported.

## Harness failures and storage

The first PowerShell 5.1 launches used ErrorActionPreference=Stop and native stderr
redirection. Progress/retry output became NativeCommandError and aborted the shell;
no ledger/candidate was created by the first GPU launch. Both failures are retained
in native-launch.log/native-prepare.log. No owned Python process remained before
retry. The second harness uses native Python subprocess capture: stderr goes to
UTF-8 logs and the actual return code decides success. All second-launch processes
completed before this evidence was committed.

C initially had about 3.4 GiB free. Private source/deps/ledgers are in
`C:/Users/Thao Nguyen/AppData/Local/HeteroES-v3-20261019`. Published weights and worker
weight caches use junctions to NEW directories under `D:/HeteroES-v3-20261019`.
D's NTFS volume identity was read and checked before writing (see protocol). No
other disk, existing runtime installation, lab state, approval or contribution
setting was changed. The existing pinned interpreter/model were read; extra deps
were installed only into the new private deps directory. No sudo was used.

Native results: private/results/windows-{full,subset,lora}-second. Large bytes:
D:/HeteroES-v3-20261019/results/windows-*-second. Raw private ledgers contain attempt
credentials and are not committed. Receipts/recipes/plans and logs are retained here.

## r11 dependency inputs and limits

`linux-pip-report.json`: 56 wheels resolved on Linux. `windows-pip-report.json`:
38 wheels resolved on native Windows. Existing exact pins plus PEFT 0.21.2,
Accelerate 1.15.0 and psutil 7.2.2. Pins and native report logs are included.
Reports are resolver INPUTS, not generated or published desktop resources. The
existing build-worker-profile.py has not been run; it still needs a safe output
option and a v3 reference/profile path. Windows report requests briefly retried
network timeouts; final native report exit is 0.

Probe helper CPU tests: 5 passed (GPU gates/comparison plus portable source paths
and private/bulk storage separation). New helper mutations and complete check-all
at 69534ec have NOT run. Last full combined CPU acceptance is e35811c, documented
in ../2026-10-19-v3-sdk. This session ended at the owner's usage-budget request.

## What this does NOT show

No cross-OS LoRA identity acceptance, complete r11 qualification/profile, installer
build/install/uninstall acceptance, deployed server switch, device enrollment,
networked heterogeneous run or learning benefit. Native runtime probes reuse the
existing pinned interpreter; they do not prove a fresh installation. Check C disk
space before attempting a second full desktop runtime.
