# Phase 3 — remove mock mode, retired routes, hosted-provider code and one-off tools

Baseline: `1fc9e57`. Work stays on `refactor/cleanup`; no live deployment or published installer is changed.

The web now always uses the Lab Server API. MSW, mock pages/scenarios/data, demo-only API functions, orphan components,
old frontend probes and their dependencies are removed. The prototype zip and notes are retained in `docs/archive/`.
Research scripts and raw runtime evidence remain; `runtime/scripts/README.md` describes their purpose.

`r10-route-scan.json` records a scan of all 72 Python files in the runtime tarball extracted from the published r10
Linux Worker installer in the deployed clone's downloads. None references the retired routes. Owner-facing device
endpoint/configuration routes, device polls and recovery transfer APIs remain. The direct monitoring-events read route
was removed; the event ingestion/deduplication test now inspects its durable table instead.

The local storage service is `RecoveryStorage` in `recovery_storage.py`; hourly metadata backups live in
`metadata_backup.py`. Restore tools have matching names. S3/R2/EC2/DuckDNS code, provider requirements and request
accounting are gone. Legacy SQLite table names and wire fields/paths such as `cloudSync` and `cloud-downloads` remain
for database and r10 compatibility. Explicit old cloud configuration is rejected instead of silently disabling storage.

Backend count: 274 → 277. Removed five cases: two EC2 provisioning checks, one S3 signing/pagination check, the unused
personal-inventory endpoint test and the token-only endpoint-update test. Added seven retired-route cases and one
cloud-configuration rejection case. All local recovery, metadata, quota, integrity, authorization and upload tests remain.
`cloud-config-red.log` and `retired-routes-red.log` show the new regressions failing before the corresponding changes.

`vulture.log` and `knip.log` are one-time audit results. Every removal was checked with `rg` across active code/tests.
Vulture's retained hits include Pydantic fields/validators, FastAPI-decorated functions, research APIs used by scripts or
tests, and platform hooks. Knip's retained files include Electron preloads loaded by filename, CLI checks invoked from
shell scripts, and test entrypoints. Its font hits are imported by shared CSS; tar and electron-builder are used by
shared setup/packaging. Local-only helper exports were made private. The orphan Worker table/registration/metrics,
dataset validator/types, metric types and scratch UI scripts were confirmed unreferenced and removed.

`mutation.log` records 3/3 killed mutants for checksum validation, storage quota and cloud-config rejection. The normal
controls pass. `check-all.log` and `checks/` record the full CPU product check. Runtime numerical code is unchanged from
the phase 2 checkpoint (2,110 CPU tests passed there, 100 GPU/optional tests skipped).

## What this does NOT show

No GPU work, native Windows run, new installer or lab deployment. Source compatibility is checked against the packaged
r10 runtime; this is not a poll from a remote device. Browser/Electron checks use disposable fixtures and recorded runs.
Audit tools are heuristic; decorated/dynamically referenced code is not deleted solely because a tool labels it unused.
