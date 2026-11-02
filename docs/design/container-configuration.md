# Backend container settings and desktop packaging

`python -m backend.apps.api|devices|storage|scheduler|all` reads private configuration when
`HETEROES_PRIVATE_CONFIG` is set, then applies explicit environment settings. `all` defaults to local authentication
and SQLite; split production roles require PostgreSQL. A role passed by the entrypoint takes precedence over
`HETEROES_SERVICE`. Existing private installations keep their settings when no override is supplied.

Environment-only operation does not require `config.json`. Set `HETEROES_STATE_DIRECTORY` to a private persistent
directory; otherwise its default is `~/.local/share/heteroes-cloud`. Defaults are agent deployment, local recovery
storage, a loopback API address and data/metadata directories below the state directory. Reading configuration does
not create files. Application startup initializes its ordinary state and storage owners.

| Environment setting                                                                                       | Configuration field / purpose                                                                                      |
| --------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `HETEROES_SERVICE`                                                                                        | Process role; default `all`                                                                                        |
| `HETEROES_STATE_DIRECTORY`                                                                                | `productStateDirectory`                                                                                            |
| `HETEROES_DATABASE_URL` or `HETEROES_DATABASE_URL_FILE`                                                   | `databaseUrl`; PostgreSQL with psycopg 3, or a persistent SQLite file for `all`                                    |
| `HETEROES_AUTH_MODE`                                                                                      | `local` or `oidc`                                                                                                  |
| `HETEROES_OIDC_ISSUER`, `HETEROES_OIDC_JWKS_URL`                                                          | Public issuer and internal no-redirect JWKS URL                                                                    |
| `HETEROES_PUBLIC_URL`                                                                                     | `publicWebUrl`, also observed by health/device responses when no private config directory exists                   |
| `HETEROES_PUBLIC_COMPUTE_URL`                                                                             | Optional public compute URL; ordinary private/public address policy still applies                                  |
| `HETEROES_BULK_API_URL`                                                                                   | `bulkApiUrl`; private control/bulk origin for device and installer paths                                           |
| `HETEROES_CREDENTIALS_FILE`                                                                               | Local bootstrap JSON: an object with a `users` map; otherwise use private `credentials.json`                       |
| `HETEROES_STORAGE_MODE`                                                                                   | `local` or `s3`                                                                                                    |
| `HETEROES_STORAGE_DIRECTORY`                                                                              | Local recovery object directory                                                                                    |
| `HETEROES_STORAGE_METADATA_DIRECTORY`                                                                     | Local metadata snapshot directory                                                                                  |
| `HETEROES_STORAGE_SIGNING_KEY_FILE`                                                                       | Local/S3 capability signing key path; share the same key across participating replicas                             |
| `HETEROES_STORAGE_QUOTA_BYTES`                                                                            | Positive integer up to signed 64-bit maximum; applied to recovery and S3 accounting                                |
| `HETEROES_STORAGE_INTERNAL_ENDPOINT`                                                                      | Internal S3 origin, including private Docker HTTP names                                                            |
| `HETEROES_STORAGE_DEVICE_ENDPOINT`                                                                        | Numeric private/LAN/Tailscale S3 origin used for presigned URLs                                                    |
| `HETEROES_STORAGE_ACCESS_KEY_ID` or its `_FILE` variant                                                   | Explicit S3 access identifier                                                                                      |
| `HETEROES_STORAGE_SECRET_ACCESS_KEY` or its `_FILE` variant                                               | Explicit S3 secret                                                                                                 |
| `HETEROES_STORAGE_REGION`                                                                                 | S3 region; default `us-east-1`                                                                                     |
| `HETEROES_STORAGE_STAGING_DIRECTORY`                                                                      | Private S3 proxy staging directory; default below state                                                            |
| `HETEROES_STORAGE_RECOVERY_BUCKET`, `HETEROES_STORAGE_DATASETS_BUCKET`, `HETEROES_STORAGE_BACKUPS_BUCKET` | Three distinct buckets; environment-only defaults are `heteroes-recovery`, `heteroes-datasets`, `heteroes-backups` |

The `_FILE` inputs for database URL and S3 credentials read at most 64 KiB and remove trailing line endings. Supplying
both a direct value and its secret file is an error. Empty, unreadable or oversized secrets fail with a generic error
containing the setting name only. Configuration and credentials are never printed. `HETEROES_STORAGE_SIGNING_KEY_FILE`
is itself a path to the shared key, rather than a file containing another filename.

OIDC mode ignores local bootstrap credentials and works without `credentials.json`. Local environment-only mode
requires explicit bootstrap credentials. Credentials seed a new installation; they do not reset existing passwords or
recreate removed users. Keep secret files outside Git. No configuration overlay writes back to the private JSON file.
Invalid existing configuration fails required reads; optional diagnostic reads fall back to an object. Values are read
on demand so public URL rotation remains visible without restarting request handlers.

Public installer manifests retain the private-transfer policy in environment-only mode. Object-store bulk transfer
still requires the private device endpoint. Enabling a public web URL does not change that policy.

## Desktop dependency and source boundary

The CPU Server profile adds only SQLAlchemy and greenlet to its existing dependency set: 23 Linux and 24 Windows
wheels. The previous Python 3.12.15 interpreter pins and all 43 existing wheel records remain unchanged. PostgreSQL,
OIDC, S3 and Prometheus dependencies stay optional and are installed through the cloud requirements for split/cloud
services. An ordinary local desktop application can start without those libraries or Torch.

Both server source builders call `backend.core.runtime_sources.server_sources`. It recursively includes backend Python
and SQL resources, including `backend/db/postgres_schema.sql`, excludes tests/cache files, and adds only the reviewed
CPU shared-runtime subset. The numerical runtime is unchanged. Refreshing source preserves reviewed wheel/Python pins;
rebuilding the profile verifies wheel hashes against the official PyPI release metadata.

Implementation modules now live in `api`, `services`, `repositories`, `db`, `core`, `storage` and `apps`. Only the stable
desktop command adapters `backend.server`, `backend.doctor`, `backend.monitor` remain at the package root beside
`__init__`. The public instrumentation attributes `backend.local_storage` and `backend.study_registry` resolve lazily to
their canonical modules. New imports should use canonical module paths.

The import-only proof compares every pre-B9 backend test/helper against its baseline. It removes import nodes for AST
comparison, rejects changes on other lines and independently checks Python commands embedded in strings. Assertions,
calls, ordinary string values and non-import code must remain unchanged. Reproduce it with:

```bash
.venv-backend/bin/python scripts/check-test-imports-only.py \
  --base e23a2963 --out .scratch/import-only-proof.json
```

Validation includes a fresh pinned private Linux interpreter, hash-checked offline installation of all 23 CPU wheels,
and real loopback HTTP health/readiness/login/session/storage checks from the extracted server archive. It verifies
that cloud/GPU libraries are absent. That result goes beyond source imports or Electron module checks. Windows wheel
hash verification is separate from actually installing/running the private Windows interpreter; the final multi-host
acceptance must state which of those it ran.
