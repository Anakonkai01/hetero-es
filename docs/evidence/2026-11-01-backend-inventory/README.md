# Backend pre-split inventory (B1)

Baseline main 6ee47147 after Part A acceptance, before backend implementation changes. The isolated application
uses disposable SQLite, local object/signing directories, no dispatcher and temporary bootstrap inputs.
No live lab DB, private state or device approval was inspected or changed.

Verified inventory: 111 unique product method/path pairs, two static mounts; proposed API 67, devices 21,
storage 23. Scheduler has no product routes. The operational health/ready/metrics routes will be common and tested
separately. Schema: 37 tables, 177 columns. AST: 358 database calls in 24 modules.
The state inventory gives an owner and replication/recovery rule for every current in-memory component.
All 62 original Python test files have a SHA-256 baseline for the unchanged-test B2 extraction proof.

The working branch architecture document publishes these inventories. IMPLEMENTATION-NOTES.md retains reviewed
transaction, packaging, S3, auth and frontend pitfalls and primary-source references for the later steps.

## What this does NOT show

This is an inventory and an ownership proposal. It does not implement the three layers, split services,
PostgreSQL, Keycloak/OIDC, MinIO, metrics, MiniCloud or cloud acceptance. Counts do not prove behavioral equivalence.
Those require implementation, original regression tests, real services and mutation evidence in B2-B10.
