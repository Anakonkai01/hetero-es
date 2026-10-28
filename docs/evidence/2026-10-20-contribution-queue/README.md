# Contribution OFF preserves queued experiments (2026-10-20)

Owner discussion: recommend keeping the queue when a computer stops contributing, so an ordinary stop or restart does
not discard experiments. Active jobs still receive safe cancellation; queued jobs wait for contribution to return.
Explicit experiment cancellation, resource revocation, account/workspace access changes and quarantine retain their
existing cancellation behavior.

## What this does NOT show

- CPU backend fixtures do not prove native desktop shutdown or GPU process termination.
- This does not add mid-generation pause/resume: running assignments use the existing safe cancellation protocol.
