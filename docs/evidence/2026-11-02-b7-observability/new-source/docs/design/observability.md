# Service observations

Every backend role serves `/healthz`, `/readyz` and `/metrics`. Keep these endpoints on the private monitoring network;
the public gateway must deny `/metrics`. They require no user session, so a failed identity provider cannot hide process
or database failures from monitoring.

`/healthz` reports that the HTTP process is alive. `/readyz` checks the product database and, when configured, storage:
local directories must remain usable, and S3 must answer checks for the configured buckets. A dependency failure returns
503 with its exception **type**, without its message, credentials or endpoint. Readiness does not assert scheduler
leadership: an available standby is ready to take over.

Install `backend/requirements-cloud.lock.txt` for split services. Each application owns a separate Prometheus registry.
The local-auth, SQLite, local-storage `all` desktop profile can run without the optional Prometheus library; in that
profile `/metrics` exposes only `heteroes_service_up`. Installing the cloud dependency enables HTTP instrumentation
there too. Split/cloud configurations fail startup if that dependency is missing.

## HTTP metrics and request records

`heteroes_http_requests_total` and `heteroes_http_request_duration_seconds` count completed requests and measure their
whole response duration, including streaming. Their labels are `service`, `method`, `route` and `status`. `route` is the
registered route pattern, for example `/api/v1/local-storage/{token}`; unmatched requests use `_unmatched`. Unknown
methods become `OTHER`. Query strings, path parameter values, request IDs and credentials are never metric labels.
The current `/metrics` request is counted after its response, so it appears on the next scrape.

Each completed request writes one JSON line to stdout with exactly these fields:

| Field                       | Meaning                                                                               |
| --------------------------- | ------------------------------------------------------------------------------------- |
| `ts`                        | UTC completion time in ISO 8601 format                                                |
| `level`                     | `ERROR` for an unexpected exception or status 500+, otherwise `INFO`                  |
| `service`                   | Selected backend role                                                                 |
| `method`, `route`, `status` | Bounded method, registered route pattern and actual response status                   |
| `duration_ms`               | Nonnegative elapsed response time                                                     |
| `request_id`                | Server-generated 32-character hexadecimal identifier, also returned as `X-Request-Id` |

Incoming request IDs are ignored. Logging does not inspect headers, bodies, query strings, raw paths or exception
messages. Unexpected endpoint exceptions produce a generic 500 response and are consumed at the ASGI boundary so the
HTTP server cannot print a second traceback containing a bearer token. If a streaming response has already started,
the record retains its actual wire status and has level `ERROR`; the status cannot be rewritten after headers were sent.
Cancellation is propagated. Disable Uvicorn's separate access log, as the role entrypoints already do.

## Business metrics

Only the `scheduler` role registers the business collector. A scrape obtains fresh database values while holding the
same operation lock as dispatch. On PostgreSQL it checks the dedicated leader connection and reads through that exact
physical session. A standby, a disconnected former leader or an inactive scheduler exposes
`heteroes_scheduler_leader{service="scheduler"} 0` and omits all business series. A live leader exposes 1. Graceful
shutdown waits for an owned read before closing that session. API, devices, storage and `all` roles never query these
business values during a scrape.

All business series include `service`. Their additional labels and units are:

| Series                                                          | Additional labels | Definition                                                                          |
| --------------------------------------------------------------- | ----------------- | ----------------------------------------------------------------------------------- |
| `heteroes_devices`                                              | `status`          | Registered devices by bounded product status                                        |
| `heteroes_devices_online`                                       | —                 | Devices seen in the preceding 30 seconds                                            |
| `heteroes_runs`                                                 | `status`          | Retained product runs by bounded product status                                     |
| `heteroes_queue_depth`                                          | —                 | Current rows in the product queue                                                   |
| `heteroes_generations_completed`                                | —                 | Sum of valid completed-generation counts in retained runs                           |
| `heteroes_candidate_attempt_errors`                             | `error_type`      | Failed attempts in retained run snapshots, grouped by the fixed failure taxonomy    |
| `heteroes_recovery_storage_bytes`                               | —                 | READY recovery-object bytes tracked in the product database                         |
| `heteroes_storage_reserved_bytes`                               | —                 | Twice the non-READY recovery-object bytes, matching recovery reservation accounting |
| `heteroes_storage_quota_bytes`                                  | —                 | Configured recovery storage quota, omitted when storage is absent                   |
| `heteroes_gpu_utilization_percent`                              | `device_id`       | Latest GPU utilization, from 0 to 100                                               |
| `heteroes_gpu_temperature_celsius`                              | `device_id`       | Latest GPU temperature                                                              |
| `heteroes_gpu_vram_used_bytes`, `heteroes_gpu_vram_total_bytes` | `device_id`       | Telemetry MiB converted to bytes                                                    |
| `heteroes_gpu_power_watts`                                      | `device_id`       | Latest reported GPU power draw                                                      |
| `heteroes_device_online`                                        | `device_id`       | Device seen in the preceding 30 seconds, 0 or 1                                     |
| `heteroes_gpu_sample_timestamp_seconds`                         | `device_id`       | Reported telemetry sample time, when available                                      |

Business observations are gauges. Run deletion or snapshot pruning can decrease generations and attempt-error counts;
they are not lifetime counters. Storage bytes describe tracked recovery objects, not every bucket's physical usage or
multipart inventory. Scraping performs no object-store listing or other network inventory call. Use the storage API
for that broader inventory and quota accounting.

Telemetry fields come from `runtime/src/heteroes/product/telemetry.py`. Missing, nonnumeric, boolean, negative,
nonfinite, implausibly large or unrepresentable values are omitted rather than reported as zero. A stale device can
retain its last observation: dashboards should show its sample age and online status alongside the value. Device
labels accept only product-generated 32-character hexadecimal IDs; names, GPU model names and raw error messages are
excluded. Unknown device/run statuses and failure kinds map to `OTHER`.

## Verification boundary

Backend tests cover normalized routes, all four non-scheduler roles, exact JSON fields, credentials in headers/body/
query/path, readiness failures, telemetry units and invalid values. A real loopback Uvicorn fixture checks that an
unhandled bearer-bearing exception reaches neither stdout nor stderr. Actual PostgreSQL tests check physical-session
identity, standby suppression, connection loss and concurrent graceful shutdown. These tests do not establish that a
Prometheus/Grafana deployment has scraped the service or that live GPU telemetry has arrived; those checks belong to
the separate MiniCloud acceptance.
