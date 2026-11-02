# B9 environment configuration, dependency packaging and shim removal

Baseline e23a2963. Hashes/patch/new source identify this implementation. Explicit settings overlay private JSON without
rewriting it. Environment-only OIDC needs no credentials.json; local authentication requires explicit seed credentials.
DB URL/S3 credential secret files are bounded64KiB, empty/missing/conflicting inputs fail safely, and no secret values
are logged. Public URL rotation and private installer manifest policy work without a private config directory. Actual
MinIO/PG factory acceptance uses these environment settings, correct three buckets and a private device endpoint.

The initial environment red log predates implementation. Optional malformed-object red records two failures during
new overlay work: the fallback retained a list instead of an object. Corrected required/optional behavior is covered.
The packaging red checks missing helper/proof and missing PostgreSQL DDL. Both builders now share recursive Python/SQL
selection, exclude tests/cache, and include postgres_schema.sql.37 physical aliases are removed; passwords and view
helpers move byte-identically into core/services. Three stable desktop CLI adapters remain. Two public instrumentation
attributes resolve lazily to their canonical modules: local_storage and study_registry. Six alias-compatibility red
failures are retained;40 focused tests pass after the lazy mapping is restored. No assertions were weakened.

The proof scans96 pre-B9 test/helper files, verifies41 changed files contain imports only, and checks two embedded child
Python programs independently. All other AST/lines stay unchanged. New proof negative controls reject changed calls,
assertions, ordinary strings and non-import lines. These new tests are listed separately, never treated as old tests.

Official PyPI hashes verify four added wheels: SQLAlchemy2.0.55 and greenlet3.4.0 on Linux/Windows. All43 existing wheel
records and both pinned Python3.12.15 interpreter records are byte-preserved. Final profile has23 Linux/24 Windows
wheels. Both private interpreter archives are downloaded/hash-checked; only Linux is installed/executed here. The fresh
Linux private prefix installs23 offline hash-checked CPU wheels, confirms cloud/GPU dependencies absent, and serves six
real HTTP checks: health/readiness/product health/login/session/metrics. Password/token remain private; the owned server
process is stopped. This is installed-package acceptance, beyond the source import and Electron module checks.

The first bundle used a stale123-file frontend/dist. The fresh desktop check builds125 web files. The bundle is
refreshed from that fresh build, then a second private prefix installs and serves all six checks. Initial/final receipts
stay separate; final-server-source-proof verifies every archive byte against current backend/shared runtime/fresh web.
The accepted final runtime SHA is2eaf0b90b8d008043f814e7c22205f1a22e6fca3514e87b6b8c2095af9f5820d.

Full actual-MinIO SQLite694/PG723 pass, zero skips, two known warnings. PG audit445 PG+52 explicit SQLite Stores; fresh
matrix container cleanup is recorded. Mutation environment17/17 (control17) and packaging/proof8/8 (control26) kill all25
syntactically valid mutants on actual PG. All24 check-all steps pass: runtime3324/1045 intentional CUDA-hidden skips,
default backend678, browser/Electron/type/lint/i18n/source packaging. Linux build-apps --check passes both shared-module
imports on its isolated source copy. It records the base e23a2963 commit while B9 is uncommitted; the patch/source hashes
identify these new bytes. No clean-source multi-host claim comes from this working-tree milestone.

## What this does NOT show

No GPU/Windows execution, deployed Keycloak, Prometheus/Grafana cluster or live deployment is claimed. Windows hashes
alone are not a Windows private installation. The native private smoke and complete clean same-source three-host matrix
remain B10, as do final main/push and all C. Installed private prefixes, test databases, credentials, Python/wheel/client
binaries and dumps are excluded; only sanitized logs/receipts/source are archived. The live lab and public revoked device
are unchanged. Owned development PG/MinIO remain available for B10. Full A->B->C completion is not claimed.
