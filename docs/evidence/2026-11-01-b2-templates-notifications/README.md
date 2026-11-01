# B2 templates, notifications and schema ownership

Baseline 499e59ac. Template validation/operations and notification projection move into services, with 5 and 16 SQL
calls in per-domain repositories. Five HTTP adapters preserve original signatures/decorators and map service errors.
The legacy in-process clean_config helper still raises HTTPException through an explicit API boundary; its business
implementation raises plain ServiceError. Template constants and the Notifications class retain compatibility exports.

SQLite migrations move byte-identically into db/migrations.py; the old module aliases that implementation until B9.
Notification table/index initialization belongs to db/projections.py, with the same two statement ASTs/order as before.
The template helper's docstring type name was corrected separately; its remaining AST is identical.

Targeted schema/migration/doctor/server/restore: 24 passed. Template and direct v3-helper regression: 47 passed.
Combined focused regression: 62 passed, plus a notification identity/read-state regression. Final full backend:
479 passed, one existing Starlette dependency warning. All 62 original test files remain byte-identical.
Mutation control: 63 passed; 11/11 mutants killed, covering forbidden settings, bool/integer distinction,
workspace/delete authorization, notification dedupe/read state, restart cursor, per-user updates, admin targeting,
legacy helper error contract and list bounds. The full pre-split product route contract still matches.

## What this does NOT show

B2 is unfinished: devices/agent, studies/qualification, storage, operations and remaining Store responsibilities still
need extraction. Database behavior is SQLite here; this does not prove PostgreSQL, multi-process service ownership,
OIDC, S3/MinIO, final packaged apps, B10 GPU acceptance, MiniCloud or deployment. Legacy imports are temporary.
