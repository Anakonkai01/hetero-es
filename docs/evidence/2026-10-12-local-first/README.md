# Local-first architecture audit evidence — 2026-10-12

This directory records the current dirty source identity and observed review
checks. It is not an installer release or acceptance of the proposed architecture.

- [audit.json](audit.json): exact heads, source manifest hash, observed CPU test
  results, known red provenance test, read-only service/storage snapshot and scope.
- [source-files.json](source-files.json): per-file source/test/configuration hashes
  and aggregate algorithm. Documentation, private state and binary assets excluded.
- [core-gpu-r2-summary.json](core-gpu-r2-summary.json): sanitized reuse of an earlier
  one-host direct-core GPU receipt, with source receipt hash and explicit limits.
- [Earlier Quick receipt](../2026-10-12-local-portability/quick-live-r1.json): live
  CPU TLS/auth/private Range probe; `gpuWork: false`.

The architecture review ran CPU checks and read-only probes only. It intentionally
did not fix runtime source, restart storage, build installers, run GPU workloads or
provision cloud. Detailed ADRs remain PROPOSED; the owner retains decision authority.
Raw latest pytest stdout is not stored here; the audit records observed results.
