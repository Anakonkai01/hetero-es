# WIP r11 reference verification — not a completed feature

Owner asked to close the session for usage budget. A staged, UNWIRED module exists:
`runtime/src/heteroes/product/qualification_v3.py`. It plans repeated positive and
negative candidate/text/restore checks plus pinned initial-adapter verification.
`tests-first.log` fails before the module exists; `tests-second.log`: 1 pure
reference-verifier test passes. Ruff passes.

Observe/qualify are NOT exercised by an integration test, not wired to desktop
qualification.main, and have no generated v3 reference. No mutation check or
check-all was run for this WIP. The new native Windows evidence shows independently
initialized adapters differ; the staged adapter check therefore needs redesign
around the canonical transferred adapter before Windows admission is enabled.

## What this does NOT show

No usable r11 profile, hardware admission, Windows LoRA qualification, installer,
new device approval or deployment. Continue tests-first from the detailed handoff.
