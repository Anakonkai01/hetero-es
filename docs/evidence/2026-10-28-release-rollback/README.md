# Rollback rehearsal for the 2026-10-28 lab release (2026-10-28)

`rehearse_rollback.py` (CPU only, temporary state, no network ports, never the live lab or its configuration) unpacks
`backend`, `scripts` and `runtime/src` of the deployed commit `82c37fca` and of the release candidate
`97f28ef1` with `git archive`, then opens ONE lab database three times, each in its own process
through `backend.app.create_app` and the lab's own HTTP routes:

1. `seed` (new code): pairs two devices (the test lab's pairing routine) and loads the recorded run
   `backend/tests/fixtures/run-d09d6ea8.json`;
2. `old` (82c37fca, the rollback target): reads devices and experiments and renames a device (`{"write": 200}` in
   `old.stderr.txt`);
3. `new` (release again): reads devices and experiments.

`report.json`: health 200 in every phase, the same experiment in every phase, and the old code's rename is visible to the
new code. Result: `ROLLBACK REHEARSAL OK`. A schema check agrees: `backend/` adds no table or column between the two commits.

## What this does NOT show

- The live lab's real database (users, devices, past runs) was not copied or opened.
- A strict (`strict_b22_v1`) run created by the release and then handled by the old code: the old code does not know that
  decoder, so the release notes say to roll back only while no strict run is active.
- Workers: device runtimes, installers and the public tunnel/Caddy path are not exercised.
- The web UI build of the old commit (the procedure rebuilds it; the rehearsal does not).
