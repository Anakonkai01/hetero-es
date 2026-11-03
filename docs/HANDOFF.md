# HeteroES — current state

One page, kept current. Start with [REVIEW-GUIDE.md](REVIEW-GUIDE.md), then the
[approved A → B → C plan](plans/codex-2026-11-review-fixes-and-minicloud.md).
Historical handoffs and immutable evidence live on `evidence-archive` ([index](EVIDENCE-INDEX.md)).

## Tóm tắt cho chủ dự án (2026-11-03)

- **Phần A hoàn tất:** đã sửa các finding review, gồm bảo mật HTTP, coordinator/restore, vùng số học đóng băng,
  ledger và khung nghiệm thu. [FINDINGS-A](review/FINDINGS-A.md) ghi từng sửa và bằng chứng.
- **Phần B và bản sửa B-021 hoàn tất. Nguồn sạch `src-c9f8f9d8…` đạt 37/37 check:** CPU 2/2, 5070 Ti 24/24,
  3060 WSL 8/8, Windows native 3/3. B-001…B-003 và B-021 đã sửa/test; B-Q1/Q2 đã trả lời.
- Noise/ES 572 test trên mỗi môi trường GPU; strict/eval 1 639 local, 1 560 WSL, 956 native; không skip.
  3060 chủ động deselect 79 ca chỉ áp dụng SM120. Qwen strict parity chung đạt cả ba môi trường.
- Throughput mới5070 Ti: short32 10 107,1 token/s, chat128 9 967,3; WSL3 104,3/2 919,5, vượt sàn đã ghim.
  137/137 mutant nghiệm thu và8/8 mutant B-021 bị phát hiện. Biên bản B10 cũ vẫn giữ nguyên, gồm lần WSL không đạt.
  Fault/replay, soak600 thế hệ và int8 đều đạt; numerical runtime không đổi.
- Backend SQLite704/Postgres733 test xanh, không skip; cả hai app Linux được build và kiểm source bytes.
  Python riêng trên Linux/Windows lần lượt cài 23/24 wheel CPU đã ghim và đạt 6 kiểm tra HTTP thực trên mỗi máy.
- **Phần C hoàn tất:26/26 PASS trên nguồn3429d810 đã ghim/rebuild**, gồm10/10 mở rộng và H1–H6. Run mới CPU+3060
  hoàn thành2 thế hệ/4 candidate; checkpoint cuối API/UI READY,3 recovery point được kiểm object thật từ MinIO.
  DOCX/PDF34 trang,5 chương,21 ảnh thật; PDF cuối đã so byte/SHA/source với MinIO. **Đã hoàn tất goal A → B → C**
  trong phạm vi kế hoạch; các việc cần tài nguyên/quyết định riêng O1–O9 có lệnh sẵn bên dưới.
- **Lab thật giữ nguyên** bản `10457f9a`, instance `34d68e114a5316bb76de9c12f657dff0`; chỉ đọc qua
  `local-lab.py status`. Thiết bị `3060-thao` vẫn REVOKED. Không dùng DB/state/cổng của lab cho cloud thử nghiệm.

## Current technical state

- Part B plus B-021 source is committed at `243f4175`; accepted B main is `3429d810b871952715bc63f94360c5f3eb2be478`.
  Final documentation/receipt edits have the same clean identity:
  `src-c9f8f9d8dc7966ca95b8c36104cffeaf2ccc030d595fc4ed71266f9c2bb92229`.
  MiniCloud keeps that exact B commit as `HETEROES_REF`; subsequent upstream handoff edits are documentation-only.
- Receipts and milestone gates: [STATUS](acceptance/STATUS.md). Final SHA-verified logs/reports:
  latest evidence `2026-11-03-b021-final-checkpoint-acceptance` (37/37,130 SHA-verified files). Previous
  `2026-11-02-b10-final-cloud-acceptance` retains38 raw records including the first WSL failure.
  Part A's immutable P-FROZEN and acceptance remain in `2026-11-01-review-fixes` / `2026-11-01-partA-cpu-ede4338e`.
- MiniCloud main is local `c32a1bd` (implementation `d181c89`). Final evidence has113 SHA-verified files at
  `~/projects/heteroes-minicloud/evidence/2026-11-03-course-wording-final/`;41 receipt/artifact/closing files are mirrored in
  `evidence-archive:docs/evidence/2026-11-03-minicloud-course-wording-final`. Its checker passes26/26 and infrastructure tests
  pass41 Python +5 Node with77/77 applied mutants killed. The unchanged Go probe's three mutants remain in foundation evidence.
- P-FROZEN: CPU 576 and GPU 694 before/after cases are byte-identical; update overhead +0.71%.
  A-014 is the approved release-state correction with old-DB migration, not a claim of unchanged ledger transitions.
- Non-strict HF FP16 has independently measured GPU references: the RTX 3060 differs from RTX 5070 Ti at one answer.
  Exact per-device references preserve all assertions; the strict golden is shared and unchanged.
- Strict lab form default: `strict_b22_v1`. Its GPU coordinator must differ from its workers (D1).
  `strict_int8_lora_v1` remains standalone/SDK only.
- CPU check-all: all 24 steps pass, including 3 324 runtime tests (1 045 intentional CUDA-hidden skips),
  688 backend SQLite tests (704 with explicit real MinIO), browser/Electron fixtures, lint/type/i18n and source-package imports.
  The latest full PostgreSQL/MinIO matrix passes733 tests, zero skips; details below.

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
  B9 complete: environment overlays private JSON and supports secret files; OIDC environment-only startup requires no
  local credentials. URL rotation and private installer transfers work without a private config directory. See
  [container configuration](design/container-configuration.md). Optional malformed-config fallback is corrected (B-018).
  Both server builders include recursive Python and SQL resources (B-019), excluding tests/cache.37 physical aliases
  are removed; password/view helpers move byte-identically and only3 stable desktop command adapters remain at root.
  Import-only proof checks96 existing test/helper files,41 changed, including2 embedded child Python imports; all
  non-import AST/lines are preserved. Its own negative controls reject weakened assertions/calls/strings.
  CPU profiles add SQLAlchemy2.0.55/greenlet3.4.0 only:23 Linux/24 Windows wheels; original Python pins and43 wheels
  unchanged. Fresh private Linux Python3.12.15 installs23 hash-checked wheels and serves6 actual HTTP checks with
  optional cloud/GPU libraries absent. Fresh desktop-built web replaces the stale source bundle; final archive bytes
  match current backend/shared runtime and all125 web files. Old and final private receipts are retained separately.
  Full actual-MinIO SQLite694/PG723, zero skips; PG audit445 PG +52 explicit SQLite Stores. Mutation17+8/25 killed,
  all24 check-all steps and Linux apps --check pass. Evidence `2026-11-02-b9-configuration-packaging`. Windows wheels
  are hash-verified; native private interpreter execution and the clean same-source GPU matrix remain B10. All C remains.
  B10 preparation:24 acceptance mutations still targeted pre-refactor backend files. They now target their canonical
  owners with original meanings/count/layout retained; the new selftest checks all137 targets exist/match once/compile.
  All59 selftests and focused16+8 mutations pass. The first CPU attempt was interrupted before its receipt and rejected;
  evidence `2026-11-02-b10-mutant-migration`.
  B10 complete: clean source8da9df22/src-aed2a90e passes all37 required check/host pairs. Full actual-MinIO SQLite694/
  PostgreSQL723, zero skips; PG audit445 PG+52 explicit SQLite Stores. All24 check-all steps, Linux app builds and
  source-byte checks pass. All137 acceptance and76 cloud mutations killed; browser OIDC fixture6 contracts pass.
  Fresh native Windows private Python3.12.15 installs24 pinned CPU wheels, passes6 actual HTTP checks and stops its
  owned process. This complements B9's Linux23-wheel/6-HTTP proof without changing either GPU environment.
  First WSL throughput failed with correct goldens; one focused repeat passed with unchanged source/floors/settings.
  Both are retained and no unproven cause is claimed. Other GPU/fault/perf/soak/int8 checks pass on the same source.
  Evidence `2026-11-02-b10-final-cloud-acceptance`; lab status before/during/after is identical, runtime source unchanged
  from Part A. B-001…B-003 fixed; architecture answers reflect implemented layers/roles/storage. All C remains.
- Authorized SSH target: `thao_nguyen@100.92.20.58` only. Private access file is outside Git, mode 0600; never print it.
- C checkpoint 2026-11-02: repo2 local đạt26/26,10/10 mở rộng và H1–H6 trên0175c93b; CPU coordinator +3060 WSL
  hoàn thành2 thế hệ/4 candidate,3 recovery point READY; có20 ảnh và DOCX/PDF34 trang. Chưa có Hub/EC2/video thực hiện.
  Đọc ảnh phát hiện B-021: snapshot cũ làm nhãn checkpoint PENDING dù storage đã xác minh READY. Đã sửa metadata
  projection,10 regression/8 mutation và SQLite704/Postgres733 xanh. Nguồn mới đã đạt37/37 và package Linux/native.
  Đây là checkpoint lịch sử trước nghiệm thu C cuối bên dưới; biên bản cũ không thay nghiệm thu nguồn mới.
  WSL needs both the matching NVIDIA driver directory and `/usr/lib/wsl/lib` as configured in acceptance/hosts.py.
  WSL/native share one GPU. Temporary test dependencies in `/tmp/heteroes-codex-testdeps-20261027-01` vanish on reboot.
- C final 2026-11-03 complete: pinned/rebuilt3429d810, new run `7a47959223334f80921f8a533f6adc5a`,26/26 PASS.
  The final checkpoint is READY in API/UI; H4 reads9 actual MinIO objects/881666 bytes. API failover, single-leader
  scheduler takeover, automatic restart after unexpected process death and actual S3 PGDMP restore pass.
  The restore backup has0 reservations; explicit Docker kill is a manual stop, separately recorded. Reward0 and unchanged
  weights prove integration, not learning. Historical terminal projections are not bulk-rewritten.
  Report: `~/projects/heteroes-minicloud/out/BaoCao-Cuoi-Ky-Cloud.docx` and `.pdf`,34 pages/5 chapters/21 actual screenshots.
  Final external receipt `evidence/2026-11-03-course-wording-final/checks/checks.json` binds the stable PDF and avoids a circular hash.
- Final original-course audit corrected C-019: the blog now visibly includes both “MyMiniCloud Blog” (HTML example/plan)
  and “MyMiniCloud – Blog” (course prose). Unit and actual HTTP red/green checks plus an independent mutant catch the
  omission. Web images, all21 screenshots, report/MinIO PDF and the full26-check receipt were repeated. Earlier evidence
  remains immutable; this text correction reuses the already accepted compute run without changing numerical/backend source.
- Closing C state:20 healthy containers,12 Prometheus targets UP,5 dashboards; two approved contributors online/ON,
  no queue or reservations. Keep the product deployment running. The bounded Windows wake request was released, with
  no power-plan edit; future WSL worker availability requires its host awake. Current state is recorded in repo2 evidence
  and `.scratch/review-2026-11/STATE.json`. The permitted live-lab status is identical before/after.

## Remaining scope and limits

- The approved A → B → C goal is complete. Docker Hub/GitHub repo2 publication, EC2, owner personal details/video,
  optional rentals and public-lab deployment remain the explicitly conditional owner actions below. No such external
  publication/deployment is claimed. The local product uses its own database/state, Docker project `heteroes-minicloud`
  and network `10.77.10.0/24`; source/archive history remains intact.
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

Các việc này là nhánh điều kiện của kế hoạch, không chặn việc chốt A/B/C local. Tại lần kiểm cuối2026-11-03:
GitHub repo2 trả401, chưa có Docker Hub login hay EC2/Tailscale EC2 do bạn cung cấp. Không tạo tài khoản/thuê máy thay bạn.

- O1: tạo repo `Anakonkai01/heteroes-minicloud` trên GitHub, chọn public/private và đăng nhập `gh auth login`, rồi:
  `cd ~/projects/heteroes-minicloud && gh repo view Anakonkai01/heteroes-minicloud && git remote add origin git@github.com:Anakonkai01/heteroes-minicloud.git && git push origin --all`.
  Repo local hiện chưa có remote; nếu bạn đã thêm thì giữ remote đúng và bỏ bước `remote add`.
- O2: tạo tài khoản Docker Hub, chạy `docker login`, rồi thay `your_namespace` bằng username thật:
  `cd ~/projects/heteroes-minicloud && scripts/push-images.sh --owner your_namespace --dry-run`;
  sau khi xem tag chạy lại bỏ `--dry-run`. Mặc định chỉ đẩy web/gateway/DNS. Backend/coordinator có Python đọc được;
  chỉ thêm `--include-source` nếu bạn quyết định công khai phần đó. Cả5 image đã build linux/amd64, tag3429d810 và course.
- O3: tạo EC2 theo C7 (Ubuntu 24.04 x86_64, 8 GB RAM, gp3 40 GB, ap-southeast-1), security group theo kế hoạch; đặt
  AWS Budget 20/50/80 USD. Điền IP/key/environment/email thật theo `config/ec2.example.json` vào file0600 ngoài repo,
  ví dụ `~/.config/heteroes-private/ec2.json`, rồi:
  `cd ~/projects/heteroes-minicloud && scripts/deploy-ec2.sh ~/.config/heteroes-private/ec2.json --dry-run`;
  xem kế hoạch rồi chạy lại bỏ `--dry-run`. Xem `docs/deploy-ec2.md` để đặt env, subnet/HTTPS và security group.
- O4 (tùy chọn): ghi khóa Tailscale EC2 vào file riêng để nối worker GPU qua mạng riêng.
- O5: điền thông tin thật trong `team.json` của repo2, thay avatar mẫu bằng ảnh được phép dùng. Trường chưa có giữ nhãn
  "mẫu". PDF báo cáo đã được dựng/upload; khi thay nội dung, dựng và nghiệm thu lại theo README repo2.
- O6: sửa bản nháp DOCX/PDF đã có trong `out/` và quay video theo kịch bản7 phút `docs/video-script.md` của repo2.
- O7: quyết định deploy bản sửa lên lab thật sau nghiệm thu. Agent không deploy lab trong kế hoạch này.
- O8 (tùy chọn): tự thuê GPU, dùng hướng dẫn đã chuẩn bị `docs/rent-gpu-worker.md` của repo2.
- O9: sửa unit đã cài bằng template đã commit khi thuận tiện:
  `install -m 644 ~/projects/heteroes/deploy/heteroes-lab.user.service ~/.config/systemd/user/heteroes-lab.service && systemctl --user daemon-reload`.
  Việc restart/deploy lab do chủ dự án quyết định riêng.
