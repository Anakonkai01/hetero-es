# Candidate6 device upgrade checkpoint (2026-10-21)

Source/package gates: `../2026-10-20-r11-candidate6/RESULTS.md`. Isolated Lab Server and Linux desktop
now run candidate6. The public r10 lab remains unchanged. All existing isolated identities are preserved.

| Device | Candidate6 install | Installed self-test | State |
| --- | --- | --- | --- |
| 5070 Ti Linux desktop | PASS | GPU PASS | OFF, idle |
| Thao native Windows 3060 | PASS, data on D: | GPU PASS twice after first failure | OFF, idle |
| Thao WSL CLI | PASS | CPU coordinator PASS | Agent stopped |
| Quang WSL CLI | PASS | Pending | Machine/Tailscale offline |

The exact installed `cpu_guard.py` SHA256 is `150ac9fdd1464e6cdb41bbc624173de28f01f53019a04f18b77e178ceb2ea95d`
on the three reachable devices. CLI runtime directory is `aa74bad820b9`; desktop profile directories are
`1e29310e07ba` (Linux) and `41bf2c06ec02` (Windows). Desktop directory identity hashes the selected
profile, so it is deliberately different from the CLI bundle-hash prefix.

Quang install exited 0, C: after install 21,084,712,960 bytes (21.08 decimal GB). No current disk reading
or new self-test is possible while offline. Tailscale read at 19:43 UTC on October 20 reports Offline,
last seen 18:20 UTC. SSH times out; the owner was asked to restore the machine/WSL/Tailscale.
Thao C: after both installations/rechecks is about 10.51 decimal GB. The original Windows Worker
backup remains untouched; no user/run/credential/model data was deleted.

Windows installer itself exited 0; the first operator verification used `resources/defaults.json`
instead of `resources/worker/defaults.json` and failed after installation. Corrected verification
checks build and runtime bundle SHA256, and both installed source and self-tests subsequently pass.

## Retained Windows qualification failure

The first new GPU self-test action at 19:36:09 UTC returned `ACTION_FAILED` after 23.8 seconds.
No detailed exception stack was available in the app's log. A temporary, restored process-only diagnostic
wrapper around selftest/quit/setup/save/startAgent then recorded all stages PASS; an ordinary unwrapped
self-test also passed. No source fix was made and the first failure remains unexplained. Do not claim
that a retry diagnosed or fixed it. A separate native Windows guarded-decoder preflight is predeclared
in `../2026-10-21-native-windows-cpu-guard/`.

Quit exited all app processes and reopening candidate6 preserved device identity, installed runtime,
self-test and OFF/drained state. The launch-control helper evaluated the inspector too early
(`ReferenceError: process is not defined`) and its PowerShell `Start-Process -Wait` waits for descendants;
the actual new app started and a separate status action succeeded. That is an operator launch-control
error, not a product startup failure. Its private waiting control session may close when the app exits.
The helper should guard `typeof process !== 'undefined'` before inspecting `process.mainModule`.
Uninstall acceptance remains after the managed run, before flag day.

## What this does NOT show

Three reachable devices passing is not all-four-device acceptance. No fresh 50-generation experiment,
audit/retry/parity acceptance, publication, merge or live deploy is claimed. The earlier Windows failure
is retained without a causal explanation. Every irreversible flag-day operation still needs explicit
owner confirmation.
