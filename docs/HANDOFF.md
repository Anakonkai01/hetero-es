# HeteroES — current state

One page, kept current. Start with [REVIEW-GUIDE.md](REVIEW-GUIDE.md), then the
[approved A → B → C plan](plans/codex-2026-11-review-fixes-and-minicloud.md).
Historical handoffs and immutable evidence live on `evidence-archive` ([index](EVIDENCE-INDEX.md)).

## Tóm tắt cho chủ dự án (2026-11-02)

- **Phần A hoàn tất:** đã sửa các finding review, gồm bảo mật HTTP, coordinator/restore, vùng số học đóng băng,
  ledger và khung nghiệm thu. [FINDINGS-A](review/FINDINGS-A.md) ghi từng sửa và bằng chứng.
- **Nghiệm thu cùng source `src-ede4338e…` đạt 37/37 check:** CPU 2/2, 5070 Ti 24/24, 3060 WSL 8/8,
  Windows native 3/3. Nguồn được nghiệm thu sạch; tài liệu và biên bản không tham gia source hash.
- Noise/ES 572 test trên mỗi môi trường GPU; strict/eval 1 639 local, 1 560 WSL, 956 native; không skip.
  3060 chủ động deselect 79 ca chỉ áp dụng SM120. Qwen strict parity chung đạt cả ba môi trường.
- Throughput 5070 Ti: short32 10 100,4 token/s, chat128 9 931,9, trên sàn đã ghim. 137/137 mutant bị phát hiện.
  Fault/replay, soak 600 thế hệ, vòng đời int8 và hai app Linux đã đạt.
- **Phần B đã xong B1–B8:** backend chia lớp, Postgres, service riêng, OIDC, S3/MinIO, metrics/log an toàn và API đồ án.
  Tiếp theo là cấu hình/đóng gói và nghiệm thu B10. Keycloak thật sẽ được nghiệm thu trong cụm phần C.
  **Phần C chưa triển khai:** repo MiniCloud, cụm container, demo GPU riêng, minh chứng và bản nháp báo cáo.
- **Lab thật giữ nguyên** bản `10457f9a`, instance `34d68e114a5316bb76de9c12f657dff0`; chỉ đọc qua
  `local-lab.py status`. Thiết bị `3060-thao` vẫn REVOKED. Không dùng DB/state/cổng của lab cho cloud thử nghiệm.

## Current technical state

- Part A is fast-forwarded and pushed on `main` at `6ee47147`; work continues on `feat/cloud-services`.
  Source fixes through `a5d81cbd` were accepted at `21d7f591`.
  Full source identity: `src-ede4338ef54a443a0ecc33a2bc96ea836ea188b856727ed63e095594a7b8b3a4`.
  The final documentation/receipt commit has the same source identity. Continue B on `feat/cloud-services` from main.
- Receipts and milestone gates: [STATUS](acceptance/STATUS.md). Final logs, reports and SHA verification:
  evidence `2026-11-01-review-fixes`; complete CPU child logs: `2026-11-01-partA-cpu-ede4338e`.
- P-FROZEN: CPU 576 and GPU 694 before/after cases are byte-identical; update overhead +0.71%.
  A-014 is the approved release-state correction with old-DB migration, not a claim of unchanged ledger transitions.
- Non-strict HF FP16 has independently measured GPU references: the RTX 3060 differs from RTX 5070 Ti at one answer.
  Exact per-device references preserve all assertions; the strict golden is shared and unchanged.
- Strict lab form default: `strict_b22_v1`. Its GPU coordinator must differ from its workers (D1).
  `strict_int8_lora_v1` remains standalone/SDK only.
- CPU check-all: all 24 steps pass, including 3 324 runtime tests (1 045 intentional CUDA-hidden skips),
  626 backend SQLite tests (641 with explicit real MinIO), browser/Electron fixtures, lint/type/i18n and source-package imports.
  The B7 full PostgreSQL/MinIO matrix passes669 tests, zero skips; details below.

## Tiến độ kế hoạch 2026-11

- 0/A0 done: preserved owner files, restored notebook, imported application findings, committed approved plan.
  Owner scratch remains `.scratch/leftover-docs-evidence-2026-10-29/`; keep model `.scratch/strict-integer-20261025`.
- A1 done: shared no-redirect HTTP client, correct per-role proxy policy; 105 focused tests and 18 mutants.
- A2 done: schema validation, resume identity, dirty coordinator and restore quarantine; 253 tests and 16 mutants.
- A3 done: finite updates, explicit reciprocal, shared input checks, ledger concurrency/release and GPU diagnostics;
  P-FROZEN proof, 16 mutants, final noise/ES and strict acceptance on all three GPU environments.
- A4 done: mandatory pytest counts, clean source identities and verifiable receipts. A5 architecture answers complete.
- A6 done: A-022/023 handle/admin-HTTP fixes; A-024 source-aware package guard; A-025 exact SM86 FP16 reference;
  58 acceptance selftests; final matrix and immutable evidence. All 10 strict notes and numerical-contract §15–17 read.
- B1 done: [architecture inventory](design/lab-server-architecture.md) publishes 111 product method/path pairs + two static mounts,
  37 tables / 177 columns, 358 SQL calls in 24 modules, proposed state/route ownership and implementation pitfalls.
  Evidence `2026-11-01-backend-inventory` uses isolated temporary state. B2 accounts/auth extracted: 467 backend tests passed, 7/7 mutants killed, all 62 original test files unchanged.
  Evidence `2026-11-01-b2-accounts`. Workspace extraction: 468 backend tests passed, mutation 6/6;
  30 SQL calls and 13 HTTP adapters separated, original tests unchanged. Evidence `2026-11-01-b2-workspaces`.
  Experiments/history/queue extracted, including 9 Store methods and unchanged timestamp AST: 477 backend tests,
  10/10 mutants; 111 product routes + two mounts preserved. B-004 hold-guard coverage fixed; original 62 tests unchanged.
  Evidence `2026-11-01-b2-experiments`. Templates/notifications + DB schema ownership extracted: 479 backend tests, 11/11 mutants; original tests unchanged.
  Schema module copied byte-identically, legacy helper HTTP contract preserved. Evidence `2026-11-01-b2-templates-notifications`.
  Devices/agent and nine Store device/scheduler methods extracted: 488 backend tests, 13/13 mutants; original 62 tests
  unchanged. Seven initial surviving mutants led to nine independent guard regressions (B-005).
  Evidence `2026-11-01-b2-devices-agents`. Studies/models/qualification extracted: 489 backend tests, 15/15 mutants;
  six request contracts preserve their ASTs, 13 HTTP adapters and 31 SQL/write-boundary calls separated.
  Evidence `2026-11-01-b2-studies-qualification`. Storage extracted: 492 backend tests, 17/17 mutants;
  recovery/ticket business and SQL, filesystem HTTP streaming, metadata snapshots and atomic publication separated.
  Original tests and instrumentation namespace preserved. Evidence `2026-11-01-b2-storage`.
  Operations/inventory/policies/validation + core contracts extracted: 496 backend tests, 12/12 mutants;
  four new access/maintenance checks, original tests unchanged. Recursive production runtime dependency closure passes
  separately; upgrade the old flat-only scanner after B2, before B9. Evidence `2026-11-01-b2-operations-core`.
  B2 complete: DB/Store/audit, diagnostics/bootstrap and application/access composition separated. Full backend 502,
  final mutation 12/12; B-006 list-owner coverage fixed. All 62 original tests unchanged, 111 routes + two mounts retained.
  All 278 unique SQL expression ASTs and the fresh 37-table/177-column schema match B1; every SQL/snapshot call belongs
  to DB/repositories. Every service imports with FastAPI/Starlette/Torch blocked. Evidence `2026-11-01-b2-composition`.
  B3 foundation: SQLAlchemy Core transaction/row/binding owner tested on SQLite and real PostgreSQL 17.11;
  full SQLite backend 520, dedicated matrix 24, protocol/engine mutation 6/6 each. Store integration and full PostgreSQL
  backend remain in progress; this is not full B3 acceptance. Evidence `2026-11-01-b3-database-foundation`.
  B3 integration: Store now uses the Core owner; portable named repository SQL, explicit ordering, real PG17 schema
  and SQLite additive migrations. Full SQLite 528 / PostgreSQL 538, zero skips; PG audit 334 real PostgreSQL Stores +39
  explicit SQLite file-contract Stores. Two product processes competing for a device/GPU grant exactly one assignment.
  Fresh `scripts/check-backend-postgres.sh` invocation passed and removed its owned container. Original assertions in
  all 70 B2 test modules remain; recursive runtime scanner and doctor instrumentation paths modernized before B9.
  Evidence `2026-11-01-b3-portable-backend`: schema/SQL mutation 12/12, integrated engine mutation 6/6; B3 complete.
  Recursive package resources/shim removal belong to B9; B5–B10 and C remain.
  B4 core: route partition/export and five role entrypoints implemented; product union remains 111 (API67/devices21/
  storage23) plus two mounts and three shared operational routes. PostgreSQL cluster identity/diagnostics persist.
  Dedicated scheduler session leadership and active/standby controller preserve job commit boundaries and fence lost
  connections; graceful and process-death takeover pass real PG tests. Core SQLite541 / PostgreSQL559, zero skips; mutation16/16. Evidence
  `2026-11-01-b4-service-scheduler-core`.
  B4 complete: PostgreSQL17 custom dumps upload to real MinIO, pass read-back checks and restore into a fresh database
  atomically with sessions revoked, reservations preserved and dispatch held. Backup mutation16/16; fixture mutation4/4.
  Full SQLite548 / PostgreSQL572, zero skips; PostgreSQL audit371 PG +48 explicit SQLite Stores. All24 check-all steps
  and Linux build-apps --check pass. The first check-all falsely reported success after fixture startup failures; it is
  rejected. Explicit seed columns and mandatory startup-failure accounting fix B-010; the replacement runs every browser
  contract and retains all seven startup logs. Evidence `2026-11-01-b4-backup-restore` records failures and final results.
  The MinIO image was built from pinned official source because the old upstream image was unavailable. Its test SDK
  adapter proves actual backup I/O; production S3 integration remains B6. Linux app checks do not prove installed private
  Python dependencies (B9/B10), Windows/GPU acceptance or deployment. B5–B10 and all C remain.
  B5 complete: RS256/issuer/audience/expiry verification, bounded no-redirect JWKS rotation/cache, kc:sub identity,
  durable approval/restriction checks and guided local-auth404. Device tokens remain independent. OIDC recovery tickets
  retain only a digest, cannot outlive JWT expiry and recheck membership/account status. Web Code+PKCE uses memory-only
  tokens, sessionStorage transaction state, callback cleanup, automatic renewal, SSO reload and provider logout.
  Full SQLite596 / PostgreSQL620, zero skips; PG audit388 real PG +48 explicit SQLite Stores. Actual-PG mutation25/25,
  frontend/harness11/11, browser protocol fixture6 contracts and all24 check-all steps pass. A counter0 refresh receipt
  was rejected (B-011); the final receipt has two code grants, one refresh and one logout. The first full PG run exposed
  a collection-time test clock and a missing packaged http_safety dependency; both are corrected with assertions intact.
  A local factory/HTTP probe passes with optional cloud/GPU imports forbidden. Evidence `2026-11-01-b5-oidc`.
  This is generated-key protocol/browser acceptance, not deployment of a real Keycloak realm. B6–B10 and all C remain.
  B6 complete: production S3Backend uses separate internal/private device clients, SigV4/path addressing, three explicit
  buckets and byte quotas including incomplete multipart parts. Dataset/model APIs and frozen device grants select
  their proper bucket. The bounded public dataset proxy preserves private bulk transfer, scoped capabilities and
  streaming cleanup; local storage accepts both metadata payload formats. S3 service union remains111 product pairs.
  Full actual-MinIO-enabled SQLite627 / PostgreSQL652, zero skips; PG audit403 PG +48 explicit SQLite Stores. Production
  S3 pg_dump upload/download/fresh restore passes with sessions revoked, reservations retained and dispatch held.
  Mutation: config8/8 and actual-PG/MinIO I/O21/21 killed; one initial private-origin mutant is equivalent because the
  signer independently enforces the same rule (separate probe retained). B-012/013 format/header-coverage issues fixed.
  Evidence `2026-11-01-b6-s3-minio`; source-package imports and lint/format pass. B7–B10 and all C remain, including the
  environment-only overlay, packaged Python dependencies and real Keycloak/GPU/deployment acceptance.
  B7 complete: every role has DB/storage readiness and private-registry HTTP counters/histograms by route pattern;
  only the live scheduler leader exports fresh DB business gauges. GPU labels/units and retained-snapshot/storage limits
  are defined in [observability](design/observability.md). JSON stdout has exactly nine safe request fields; a real
  Uvicorn transport test rules out bearer-bearing traceback leaks. Concurrent owned reads survive graceful scheduler
  shutdown; invalid/unrepresentable telemetry and generation values cannot break scrapes (B-014/015).
  Final actual-MinIO SQLite641/PostgreSQL669, zero skips; PG audit418 PG +50 explicit SQLite Stores. All24 resumed
  check-all steps pass, including browser/Electron fixtures; the interrupted first run is rejected. Mutation31/31 killed
  on actual PG after fixing the counter-value test gap (B-016); initial26/27 retained. Evidence
  `2026-11-02-b7-observability`. Desktop without optional Prometheus keeps basic service_up only; split/cloud requires it.
  B8–B10 and all C remain; no live monitoring/GPU/Keycloak/deployment acceptance is claimed by these CPU fixtures.
  B8 complete: opt-in API-only hello/secure/student/students-db routes; flask-app JWT verification is independent of
  lab accounts. Mounted JSON is fresh/bounded; fixed student SQL uses a separate read-only PG transaction and role.
  Full actual-MinIO SQLite665/PostgreSQL694, zero skips, PG audit441 PG +50 explicit SQLite Stores. After whole-suite
  collection, one independent oversized-valid-prefix regression was added; final focused SQLite25/PG26 and actual-PG
  mutation15/15 pass (initial14/15 retained, B-017). Production source did not change after those full suites started.
  Source-package imports and lint/format pass; default111 routes remain exact. [Course API guide](design/course-demo.md)
  and evidence `2026-11-02-b8-course-api` record the configuration and real read-only-role proof. The last whole24-step
  browser/Electron check is B7; B8 changes only the disabled-by-default API feature. B9–B10 and all C remain.
- Authorized SSH target: `thao_nguyen@100.92.20.58` only. Private access file is outside Git, mode 0600; never print it.
  WSL needs both the matching NVIDIA driver directory and `/usr/lib/wsl/lib` as configured in acceptance/hosts.py.
  WSL/native share one GPU. Temporary test dependencies in `/tmp/heteroes-codex-testdeps-20261027-01` vanish on reboot.
- Temporary Windows wake request is bounded (no power-plan edit). Live handles, expiry/renewal note and stop flags:
  `.scratch/review-2026-11/STATE.json`. Renew a bounded lease only while remote work needs it, release after remote work.

## Remaining scope and limits

- B1–B8 are complete. Execute B9–B10 then C1–C8 in the approved order. Publish the final B commit as MiniCloud's `HETEROES_REF`.
  Test cloud on its own database/state, Docker project `heteroes-minicloud` and local network `10.77.10.0/24`.
- Existing separate milestones remain truthful: managed-runner M3.bookkeeping needs measurement;
  M1.architectures and M3.full-disk remain deferred. Part A does not deploy the new source.
- Two strict workers in one process on one GPU remain an unsupported graph-capture layout; the lab avoids it.
- The installed user unit still needs the owner action O9 below; its committed template already uses backend venv Python.

## Commands

```bash
export ACCEPT_PYTHON="$HOME/miniforge3/envs/heteroes-match/bin/python"
python3 scripts/accept.py run cpu --keep
HETEROES_GPU_ACCEPTANCE=1 python3 scripts/accept.py run gpu perf faults package mutation --keep
python3 scripts/accept.py remote 3060-wsl gpu perf --keep
python3 scripts/accept.py remote 3060-native gpu --keep
python3 scripts/accept.py report --write
python3 -I "$HOME/.local/share/heteroes-lab/app/scripts/local-lab.py" status
```

Run WSL/native serially. Check live-lab status before GPU work; do not benchmark alongside GPU or heavy CPU work.

## Việc của chủ dự án

Các việc này không chặn phần A/B. Lệnh repo 2 sẽ chạy sau khi repo và scripts được tạo ở phần C.

- O1: tạo repo `Anakonkai01/heteroes-minicloud` trên GitHub, rồi:
  `cd ~/projects/heteroes-minicloud && git remote add origin git@github.com:Anakonkai01/heteroes-minicloud.git && git push origin --all`.
- O2: tạo tài khoản Docker Hub, chạy `docker login`, ghi username vào file riêng; sau C5 chạy
  `cd ~/projects/heteroes-minicloud && scripts/push-images.sh`.
- O3: tạo EC2 theo C7 (Ubuntu 24.04 x86_64, 8 GB RAM, gp3 40 GB, ap-southeast-1), security group theo kế hoạch; đặt
  AWS Budget 20/50/80 USD. Ghi IP và đường dẫn khóa SSH vào file riêng; sau C7 chạy `scripts/deploy-ec2.sh` ở repo 2.
- O4 (tùy chọn): ghi khóa Tailscale EC2 vào file riêng để nối worker GPU qua mạng riêng.
- O5: điền thông tin thật trong `team.json` của repo 2 và cung cấp avatar/PDF; trường chưa có giữ nhãn "mẫu".
- O6: sửa bản nháp báo cáo và quay video theo `docs/video-script.md` của repo 2 sau C8.
- O7: quyết định deploy bản sửa lên lab thật sau nghiệm thu. Agent không deploy lab trong kế hoạch này.
- O8 (tùy chọn): tự thuê GPU, dùng hướng dẫn `docs/rent-gpu-worker.md` của repo 2 sau C8.
- O9: sửa unit đã cài bằng template đã commit khi thuận tiện:
  `install -m 644 ~/projects/heteroes/deploy/heteroes-lab.user.service ~/.config/systemd/user/heteroes-lab.service && systemctl --user daemon-reload`.
  Việc restart/deploy lab do chủ dự án quyết định riêng.
