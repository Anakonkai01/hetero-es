# B2 workspace HTTP, business and repository extraction

Baseline 74deec97. Extracted 30 SQL calls into WorkspacesRepository, 17 business functions into the workspace service,
and 13 HTTP adapters. Root routes_workspaces remains a temporary compatibility import. Repository driver conflicts
become plain DatabaseConflict errors; the service maps expected conflicts to the existing public response.

The AST proof checks unchanged function bodies except the explicit repository calls, plain service/conflict errors,
dependency parameters and HTTP response removal. HTTP signatures/decorators match the baseline. Existing comments
are preserved. The proof caught an instrumentation mismatch for chained fetchone calls before source publication;
the extractor was corrected to distinguish the inner execute call. The intermediate instrumentation test is retained.

Focused regression: 27 passed. Full backend: 468 passed, one existing Starlette warning. All 62 original Python test
files remain byte-identical. Mutation control 27 passed; 6/6 killed: create/list permission, rejected join membership,
invitation identity, membership run cancellation and repository conflict translation.

## What this does NOT show

The overall B2 split is unfinished. This still includes the legacy queue projection in the workspace installer;
its placement will be completed with the experiment/history/queue domain. Store's remaining methods and other domains
still need extraction. This does not prove PostgreSQL, split service runtime, OIDC, MinIO, packaging or B10 acceptance.
