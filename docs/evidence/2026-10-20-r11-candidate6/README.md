# r11 candidate6 — FP32 GPU generation with selective CPU reference

Replacement for candidate5, which stopped its managed acceptance on a reproduced cross-GPU FP32 greedy
near tie. The owner approved the separately identified `hf_fp32_cpu_guard_v1` decoder for implementation
and further validation. Old decoder meanings and frozen noise/update/ledger behavior remain unchanged.

Build only after the final combined CPU gate and expanded two-GPU decoder probe pass. Planned build:
`lf1-20261020-r11-candidate6`, fresh Archive output directory; verify UUID 10443D1F443D094C before writing.
Preserve pinned Python/wheel/model identities. Prepare installers with `--prepare-only`, compare every
runtime source byte, require the new CPU-reference module in the Worker archive, run source-copy packaging
and packaged Linux Server/Worker checks. Retain original candidate5 files and failed-run evidence.

Then upgrade the four isolated test devices, recheck actual free C: space and runtime identities/self-tests,
and run a fresh, predeclared 50-generation managed acceptance with real audits and the planned Quang outage.
Contribution remains OFF during upgrades. Quit/relaunch/uninstall is still required before the flag day.

## What this does NOT show

This predeclaration is not a build, hardware or release receipt. No public installer publication, live deploy,
merge or live device change is authorized by an installer build. Each irreversible flag-day action still
requires the owner's explicit "đồng ý". The CPU margin gate is empirical, not a universal error bound.
