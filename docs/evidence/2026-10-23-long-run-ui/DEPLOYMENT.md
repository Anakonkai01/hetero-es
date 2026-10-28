# Public deployment and acceptance

Deployed backend and web source: `82c37fcae4e643804a5f7e6d8e1147523516c88a`.
The source commit includes the earlier connector and GPU-name repair.

- `publication.json` records the index/asset hashes and the private rollback backup.
- Deployment used the deployed `scripts/local-lab.py` lifecycle functions under
  its exclusive lock, idle check and temporary admission hold. No GPU was started.
- Existing static assets and downloads were preserved. The prior index and a
  private database backup were retained for rollback.
- The two run bodies and snapshots have identical hashes before and after
  deployment. Corrections are read-only reporting projections.
- `public-settled/receipt.json` accepts both actual public runs after waiting for
  the separate generation-history request. Totals, audit coverage, stopped state,
  scoped event history, diagram/table and chart density pass at desktop/tablet/
  mobile viewport sizes, with no browser page errors.
- The earlier public probe in `public-after/` asserted before the generation
  history arrived; it captured the initial empty chart and is retained. The
  successful probe explicitly waits for the reward chart before checking labels.
- The live source remains at `82c37fc`; subsequent evidence/handoff commits do not
  require a service restart.

The oomd cause and two audit timeouts are still open operational issues. This
deployment corrects their presentation and preserves their evidence.
