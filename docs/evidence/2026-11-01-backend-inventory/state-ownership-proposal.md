## Pre-split inventory (prepared from source, 2026-11-01)

The isolated baseline app has 111 method/path pairs and two StaticFiles mounts. Its fully initialized product schema
has 37 tables and 177 columns. AST inspection finds 358 execute/executemany/executescript calls in 24 backend modules.
The baseline was constructed in a temporary directory with a temporary signing key, local object directory and SQLite
file. No live lab state or database was read. The complete baseline snapshots are retained with the B1 evidence.

| In-process state | Current source | Decision for split deployment | Recovery / replication rule |
| --- | --- | --- | --- |
| Password/registration throttles | app.py, throttle.py | Keycloak owns cloud password and registration throttling; keep existing counters in local all mode. | OIDC disables the local credential endpoints. API replicas therefore hold no cloud credential throttle state. |
| SSE active connection count and pacing | live.py LiveStreams | Keep per API replica as a resource limit. | Timeline content comes from persisted run/snapshot data. Reconnecting to another replica rebuilds the stream; the counter is not business state. |
| One upload's file handle, digest, partial path and cancellation lock | local_storage.py _Upload | Request-scoped state in the single storage service. | A lost request leaves no committed object; retry uses the signed grant. Local partial files are never treated as published objects. |
| Storage signing key and path configuration | local_storage.py LocalBackend | Single storage owner for local mode; S3 uses shared configured endpoints and credentials. | Keys/configuration survive process restarts in private mounted state. API services do not own upload file descriptors. |
| Recovery quota lock and pending verifier set | recovery_storage.py RecoveryStorage | Keep in the single storage service; all upload/verify/delete routes belong there. | Durable point/object/ref status remains in DB. An interrupted verifier can be retried; the set only suppresses duplicate local threads. |
| Recovery verification threads | recovery_storage.py verify_background | Storage owns them. | A process restart cannot manufacture READY: object hashes and manifest publication remain the evidence of success. |
| Metadata backup timer/thread and local staging paths | metadata_backup.py, app.py lifespan | Storage runs one loop; PostgreSQL mode uses pg_dump and the backup bucket. | Completed manifests and backup status are durable. Restore is an explicit isolated operation, never an automatic overwrite. |
| Writer file descriptor | writer_lock.py | Keep kernel lifetime lock for production all + SQLite. Split production services use PostgreSQL. | PostgreSQL serializes business writes with advisory transaction locks across all services. |
| Store.lock | store.py | Keep a process RLock for SQLite; DB layer owns transaction serialization. | Reentrant calls share transaction ownership to avoid a second writer inside an open write. PostgreSQL uses one lab write lock key. |
| Store.operation_lock and dispatch loop | store.py dispatch_once/dispatch | Scheduler owns dispatch. One PostgreSQL session advisory leader lock admits the active scheduler; another waits. | Loss of the owning connection releases leadership. A new leader reconciles durable assignments/reservations before admitting work. |
| Store.last_error | store.py | Persist scheduler diagnostics for other processes; retain the local facade for desktop compatibility. | API replicas must not report their empty local cache as scheduler health. |
| AgentRuntime references and configuration | devices.py, agent_commands.py, agent_polling.py, agent_scheduling.py | Each service may construct the facade; device commands, membership and reservations stay in DB. | No process-local device ownership is authoritative. Every state-changing operation uses the cross-process write transaction. |
| Model probe ownership | model_qualification.py | Retain probe jobs and device/physical reservations in DB. | HTTP process death does not release a GPU. Admission still requires observed ownership release. |
| Registry | study_registry.py | Database repository plus storage backend, without an authoritative memory cache. | Asset and upload rows remain shared across replicas. |
| Notification cursor and dedupe | notifications.py | Already persisted in settings/notifications; execute catch-up transactionally. | Unique dedupe keys and the shared write transaction prevent duplicate projections across API replicas. |

The proposed method/path ownership is API 67, devices 21 and storage 23. The storage exceptions below /device/ are
explicit: /device/recovery-points belongs to storage, while device study/model transfer grants belong to devices.
User-facing artifact routes, dataset upload/build routes and model upload/publish routes belong to storage. Ordinary
experiment, model inventory, qualification request and account/workspace routes belong to API. Web mounts and installer
manifest remain part of all for desktop compatibility and are served by web containers in MiniCloud.

Common health, readiness and metrics endpoints are operational routes on every process. Product-route union/equality
must be checked separately from these deliberately shared diagnostics. Scheduler exposes no product route.
