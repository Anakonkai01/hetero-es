# B10 final same-source cloud backend acceptance

Committed source8da9df22, identity src-aed2a90eb9b727bee281c5540fcfbdba5395ccb7e13dee69a9ad8d04c914a3c2.
All37 required check/host pairs PASS on this same clean source: CPU2; local GPU/fault/package/mutation21 plus perf3;
RTX3060 WSL8; native Windows3. Six byte-preserved receipts have38 raw records because the first WSL throughput failed
and its focused repeat passed. The latest result per check/host determines the37 selected successes. Every raw check
log was SHA-verified against its receipt before archival. Redaction records preserve original/archived hashes.

GPU noise/ES572 passes on each environment. Strict/eval1639 local,1560 WSL,956 native; zero skips. Both3060 suites
explicitly deselect79 SM120-only cases. Qwen strict parity passes all3 environments; Smol/Tiny, memory/phase checks
pass where registered. Local short32/chat128 means10087.3/9899.5 token/s exceed9873.1/9753. WSL final3085.9/2915.9
exceed3041.6/2867.2. The first WSL means1653.2/1530.2 failed, with correct golden token hashes. One focused repeat
passed without code, floor, global power-plan or other settings changes. The first failure remains; its cause is not
proven. AC was online/energy saver off; no unrelated process was stopped. NVIDIA documents limited WSL NVML queries:
https://docs.nvidia.com/cuda/wsl-user-guide/index.html . These observations do not establish a specific cause.

Fault/replay and600-generation soak pass, as does int8 lifecycle. All12 numerical/product mutation groups kill137/137;
24 migrated backend guards and their preflight failure/59-selftest fix are preserved in the preceding B10 migration
folder. Final CPU includes59 selftests, all24 check-all stages, runtime3324 passes/1045 intentional CUDA-hidden skips,
backend678 default passes and actual browser/Electron contracts. Complete CPU child logs accompany the parent receipt.

Cloud auxiliary acceptance on this source: full actual-MinIO SQLite694/PostgreSQL723, zero skips. PG audit445 PG+52
explicit SQLite Stores; its fresh owned matrix container was cleaned. Additional engine6/service16/OIDC25/S3config8/
S3IO21 mutations kill76/76 on actual PG/MinIO where relevant. One B4 tick-session mutation now matches its complete
statement because B7 added another session substring; meaning/count retained in provenance. The actual OIDC library
browser fixture passes6 contracts with real refresh/code/logout counters. This remains a protocol fixture, not Keycloak.

Linux package check builds both Electron apps and proves their runtime bytes match source. A fresh private Linux CPU
interpreter installed23 pinned wheels and passed6 HTTP checks in B9. Here a fresh native Windows Python3.12.15 installs
24 pinned CPU wheels and passes the same6 actual HTTP checks, with cloud/GPU packages absent. Its private prefix is
separate from the existing GPU environment; the owned HTTP process was stopped. Installation logs/receipt are included;
no private interpreter/state/binaries are archived. Windows NSIS installers were not rebuilt/published by this check.

Numerical runtime source is byte-unchanged from accepted Part A, so its immutable P-FROZEN proof remains applicable;
this matrix additionally executes the current aggregate source. Architecture and source-layer tests preserve the
111 default product routes, separate operational routes, SQLite desktop behavior, actual PostgreSQL transactions,
leader fencing, OIDC/S3/metrics/course functionality and dependency boundaries. The live lab's permitted status before,
during and after is identical; no deployment, unit edit or device approval/contribution change was made.

## What this does NOT show

This closes the implementation/acceptance of Part B. It does not establish the yet-unbuilt MiniCloud repository,
real Keycloak realm, Prometheus/Grafana/Loki deployment, multi-container course/GPU demo, EC2/Docker Hub publication,
report DOCX or video. All C remains. Separate managed-runner bookkeeping, architecture/full-disk deferrals and owner
live-deploy work remain as documented. No learning result is claimed. Private keys, credentials/access identifiers,
signed capabilities, databases/dumps, models and client/interpreter binaries are excluded. The whole A->B->C goal is
still active; this milestone's main FF/push and final HETEROES_REF are recorded by the controller after its commit.
