# HeteroES-LLM — detailed context handoff for Claude architecture review

> **Update 2026-10-12 evening — implementation resumed.** After the review the owner decided
> D1 to D8 (recorded as DECIDED inside ADR-004 to ADR-007) and asked for a working product that
> night. Work is on branch `feat/local-first-lf1` of both repositories (nothing pushed): the
> doctor, public installer downloads, the replay-only worker on the public route, login and
> registration throttling, the named-tunnel manager, and build lf1-20261012-r3 with its evidence in
> [evidence/2026-10-12-lf1](evidence/2026-10-12-lf1/README.md). The review text below is kept as
> written; where it says "pending" or "not implemented", check that evidence folder first.

Date: 2026-10-12. Audience: Claude as Distributed Systems Architect / ML Systems
Engineer. This document is standalone context for a review, not authorization to
implement the architecture. Communicate with the owner in Vietnamese; repository
documentation is English.

## 1. Your task and the owner's decision authority

Read the current repositories and evidence, audit the architecture, challenge the
proposal and present alternatives with trade-offs. **Do not write runtime code,
fix tests, change services, provision cloud, build/publish installers, run GPU
campaigns, commit, push, merge or tag during this review.** Read-only inspection
and architecture documentation are the current scope.

The owner specifically asked whether the assistant was auditing or deciding the
architecture itself. The answer was: audit plus draft recommendations; the owner
retains decision authority. The latest instruction was to finish this work and
prepare detailed context for Claude. Do not interpret “okay, continue” as approval
of any particular database, process topology, offline contract or ADR.

The desired direction supplied by the owner is:

- Local-first, self-hostable, cloud-optional and provider-neutral.
- A lab should ultimately operate fully on its own infrastructure, without AWS,
  Cloudflare, a domain or mandatory Internet access.
- Preserve deterministic ES, leases, ledger, replay, recovery and historical proof.
- Avoid Kubernetes, a full SaaS, distributed database or speculative infrastructure.
- Keep the owner in control of cloud setup and architectural decisions.

The current proposal and ADR-004..007 are all **PROPOSED**, not approved decisions.
Your role includes finding incorrect assumptions and recommending changes, rather
than simply endorsing the previous assistant's design.

## 2. Project purpose and limits

HeteroES-LLM post-trains small language models with distributed synchronous
Evolution Strategies on heterogeneous consumer GPUs, including RTX 5070 Ti,
RTX 3060 and GTX 1660 Super. Workers evaluate independently perturbed candidate
models and return rewards. The coordinator owns canonical weights, accepts
candidate results, computes the ES update and persists numerical history.

Each worker holds a full model replica. The project does not pool VRAM or shard
one model across devices. It is currently a trusted-lab system. Per-device
authentication is not proof that a worker computed an honest reward. Do not claim
robustness against malicious public volunteers, speedup, positive learning gains,
large-scale stability or hosted multi-tenancy without the relevant evidence.

The engineering questions are admission/capability (C1), candidate scheduling
(C2), lease/attempt correctness (C3), and canonical-state synchronization/recovery
(C4). Recipe v1 numerical serialization, noise engine, update records, hashes and
golden baselines must remain intact. Product scheduling does not own ES math.

## 3. Source identity: the old GitHub handoff is insufficient

Historical research repository: `https://github.com/Anakonkai01/hetero-es`.
The earlier web-chat handoff referred to branch `feat/to-90-c1-profile` and commit
`bb0ce420c21e10b3b9b13e3e494ce41453030420`. That local commit was inspected, but
it predates substantial product management, device identity and lifecycle work.
Do not treat its statement “control plane not implemented” as current fact.

| Track | Active checkout | Branch | HEAD at audit |
| --- | --- | --- | --- |
| A: numerical/runtime/product agent | `/home/pc5070ti/projects/hetero-es-m3-runtime` | `feat/local-lab-completion` | `d5bbedb4ff53cddbc2f4c9c63cc51051af44f711` |
| B: management/Web/desktop/release | `/home/pc5070ti/projects/Hetero-ES-LLM-m3` | `feat/local-lab-completion` | `023967c41f4df26047adc8498976d8dda2caaf20` |

**Both trees have uncommitted implementation from before the architecture pause.**
HEAD alone does not identify the audited source; nothing in this continuation has
been pushed/merged/tagged. The integration/research checkouts are preserved and
are not the active product source. The owner has two collaborating project tracks;
the product repository is essential to the audit even if only Track A is public.

The [audit receipt](evidence/2026-10-12-local-first/audit.json) captures heads,
dirty status, observed checks and a read-only operating snapshot. The
[source manifest](evidence/2026-10-12-local-first/source-files.json) includes
187 Track A and 258 Track B source/test/configuration files, with per-file hashes.
Aggregate hashes:

```text
A: 56863c7349a46d8bd9b39e969a2c47d16a3726e3559701aae0065c249aa5290c
B: 21ec606f93f6738b182f833aa127d89d06f9b6a66fa13349f4abd5a3a040511a
```

These hashes exclude documentation, ignored binaries/assets and private runtime
state. They identify an audit snapshot, not a released build or supply-chain
attestation. If you only have GitHub access, explicitly state that you cannot
verify the current dirty product/runtime source. Use the provided review snapshot
when available; never invent access to either checkout or private receipts.

## 4. Reading order and module map

1. This handoff, then the [audit/proposal](local-first-architecture.md).
2. Track A [MASTER](../../hetero-es-m3-runtime/HETEROES_LLM_MASTER.md) and
   [STATUS](../../hetero-es-m3-runtime/HETEROES_LLM_STATUS.md). Their top-level
   2026-10-12 notices supersede old execution orders.
3. Proposed [ADR-004](../../hetero-es-m3-runtime/docs/adr/ADR-004-local-first-deployment.md),
   [ADR-005](../../hetero-es-m3-runtime/docs/adr/ADR-005-state-and-lifecycle-authority.md),
   [ADR-006](../../hetero-es-m3-runtime/docs/adr/ADR-006-offline-network-and-storage.md),
   [ADR-007](../../hetero-es-m3-runtime/docs/adr/ADR-007-identities-versions-and-recovery.md).
4. Actual source and tests listed below; inspect the uncommitted changes too.
5. Dated [M2 evidence](m2-implementation.md),
   [local progress](local-lab-progress.md),
   [prior continuation spec](local-cloud-portability.md),
   [historical session close](m3-session-handoff.md) and audit evidence.

| Concern | Track A | Track B |
| --- | --- | --- |
| ES numerical correctness | `coordinator.py`, `executor.py`, `generation_record.py`, numerical/noise modules under `src/heteroes/` | Consumes frozen runtime configuration; does not own ES update |
| Training ledger/recovery | `src/heteroes/ledger/`, `replay.py`, `product/recovery.py` | Management projections and object metadata |
| Worker compute | `worker_api.py`, `worker_runtime.py`, `http_transport.py`, `scripts/run_worker.py` | Device identity, selected assignment and transfer authorization |
| Process/lifecycle | `product/agent.py`, `gateway.py`, `runner.py`, `desktop_bridge.py` | `backend/devices.py`, `store.py`, lifecycle routes in `app.py` |
| Accounts/workspaces/management | Existing product contracts | `backend/app.py`, `lab.py`, `store.py`, `devices.py` |
| Storage | Runtime snapshots and immutable publication | `backend/local_storage.py`, `cloud_storage.py`, download/grant routes |
| CPU hosting | No CUDA requirement for management | `backend/server.py`, `deployment.py`, `deploy/`, `scripts/local-lab.py` |
| Desktop/release | Agent/self-test/runtime source packaged by B | `desktop/worker/`, `desktop/server/`, frontend, build/verify helpers |
| Paused M5/v2 continuation | `study/`, qualification, frozen generation contexts | `backend/study/`, `study_registry.py`, assets/config UI |
| Monitoring | `product/telemetry.py`, `windows_detail.py`, energy collector | Vendored `backend/monitoring/`, Web/desktop UI |

Most Track A paths in this table are relative to `src/heteroes/`. Strict older
clients and provenance validation make apparently additive fields consequential.
Do not reorganize files merely to make an architecture diagram look cleaner.

## 5. What currently exists

### Compute plane

The coordinator keeps canonical model weights and its SQLite training ledger.
Workers pull leases over HTTP, heartbeat and submit typed results/failures.
Lease attempts and authenticated ownership govern acceptance; errors are not
converted into zero reward. Update records are persisted before applying canonical
updates. Recovery and deterministic replay maintain model lineage. Update replay
lets workers receive small generation updates instead of repeated full weights.

Replay is bounded and may fall back to full model synchronization. The legacy
research HTTP CLI retains shared bearer-token support; the product assignment
path adds individual bound worker credentials. These are distinct deployment paths.

### Existing management/product plane

The current product already has a CPU backend with management SQLite, accounts,
workspaces/membership, admin approval, experiment history, queue and dashboard.
Device enrollment uses one-use pairing, private device credentials/token digests,
approval/revoke, explicit contribution and boot-scoped ON. A user's `worker_id`
payload is not the sole authentication authority in the product path.

Experiments explicitly select a qualified coordinator. Coordinator selection is
not fixed to the 5070 Ti; the CPU Web/API can run independently of GPU execution.
Agents poll typed commands and report state. Physical coordinator/worker resources
are reserved atomically, with assignment epochs and process ownership checks.
Lost heartbeat is not authorization to release a GPU or launch a replacement.

The system has local and S3-compatible object-storage mechanisms, private backup/
restore, quotas/retention and generation-boundary recovery. Local identity,
workspace isolation and physical reservations do not establish multi-lab tenant
isolation or prevent the same GPU from being enrolled in independent installations.

### New source preserved but not fully released

Earlier authorized continuation added separate public-control/private-bulk URLs,
headless CPU entrypoint, provider-neutral endpoint configuration and temporary
Quick Tunnel helpers. Idle endpoint changes preserve identity only with OFF/drain
guards. Proxy listeners accept the forwarded Host and restrict public bulk routes.

It also added pinned model/data manifests, mapped JSON/JSONL/CSV data and deterministic
splits/batches, Recipe v2 wrapping the v1 numerical base, constant/cosine sigma,
frozen per-generation contexts, validation-only checkpoint selection, locked final
test, sampled metrics and HF export/reload checks. The product includes registry,
transfer authorization and UI work. This is experimental source, not a fully
qualified shipped M5 feature. Model-name support is not model qualification.

New Windows detail monitoring exists in source and fixtures. Native Windows
acceptance of that new collector/build has not happened. Windows remains the
historically qualified Recipe v1 worker-only profile; no Windows coordinator/v2
claim is permitted from the Linux work.

The v2 generation-context table is added while the ledger schema remains 5.
Assess old/new binary compatibility and unsupported downgrade behavior explicitly;
an unchanged schema integer does not prove semantic compatibility.

## 6. Measured evidence and limits

| Evidence | Observed result | Does not establish |
| --- | --- | --- |
| Fresh runtime CPU suite | 2,074 passed, 100 skipped; exit 0; 74.32 s | GPU/native package or offline deployment acceptance |
| Fresh product backend suite | 109 passed, one failed; exit 1; 12.15 s | A green shipping baseline |
| Known backend failure | `test_vendored_collector_provenance_matches_files` expects four modules; new `windows_detail.py` makes five | A runtime failure by itself; fix/review is still pending |
| Earlier desktop/frontend checks | Combined desktop checks passed; Web build/lint passed before review | Newly built or natively exercised current installers |
| Historical M2 three-device experiment | 20/6/10 accepted candidates across three GPUs; final hash matched single-GPU baseline | Simultaneous independent jobs, scaling or speedup |
| Historical M2 management outage | API unavailable 40.055 s; generation progress and reconciliation recorded | Every launch/recovery/drain partition case |
| Live Quick CPU probe | HTTPS Web/compute, credential rejection, bound worker identity, public bulk denial, private 206 Range/hash verified | GPU work, long-term tunnel reliability or Internet-only bulk |
| Earlier standalone core GPU r2 | v1 baseline vs boundary pause/restart matched rewards, update hashes and final weights; v2 contexts/export/HF reload passed | Product desktop lifecycle, remote GPUs, other models, Windows v2, multi-job acceptance or learning gain |
| Older native Windows RTX 3060 | Historical v1 worker acceptance | The newest uncommitted build or monitoring/v2 parity |
| Published installers | `monitor-20261011-r2` remains current | The 2026-10-12 dirty source is packaged |
| Real AWS/R2 deployment | Not performed | Any production cloud acceptance |

Exact CPU commands and result caveats are in the audit receipt. Raw stdout from
these latest pytest checks is not retained there. Existing historical negative
learning findings remain part of the research record; do not discard them.

The [Quick receipt](evidence/2026-10-12-local-portability/quick-live-r1.json) records
2,300,000 Range-transferred bytes with SHA-256 verification and `gpuWork: false`.
The [sanitized GPU summary](evidence/2026-10-12-local-first/core-gpu-r2-summary.json)
derives from the owner's private `20261012-r2/acceptance.json`, includes its hash,
and records hardware/scope. That earlier run took 152.9287347793579 s on one
5070 Ti host. It is reused evidence, not a GPU run made during this audit.

## 7. Current operating state: preserve it

Read-only snapshot at audit:

- 21 historical experiments retained, dispatch held, zero physical reservations.
- Local `5070ti` contribution enabled=false, desired=false; no NVIDIA compute PIDs.
- CPU Web/API and temporary Web/compute Quick Tunnels running; monitoring Agent stopped.
- No active GPU coordinator serving training. The Quick probe's temporary CPU
  coordinator was stopped after the probe.
- Stable server instance ID persists through the temporary endpoint configuration.
- Private config has `storageMode: local` prepared, but live health reports
  `recoveryStorageMode: null`. The running backend has no active storage backend;
  **configuration preparation is not storage activation**. No service cutover was
  performed during architecture review.

Operational private paths are references for an authorized local continuation,
not attachments to share:

| Item | Location / constraint |
| --- | --- |
| CPU configuration and management state | `~/.config/heteroes-m2/`, `state/product.sqlite`; protected ext4 |
| Agent private config | `~/.config/heteroes-private/ui-local-agent/config.json`; includes a device credential |
| Prepared large local object storage | `/mnt/Archive-2tb/heteroes-local/artifacts/lab-storage-20261012` |
| Prepared protected metadata storage | `~/.config/heteroes-m2/state/metadata-objects` |
| Storage pre-change backup | `state/product-before-production-20261012.sqlite`, private config snapshots under `local-deployment/` |
| Earlier standalone GPU receipt | `~/.local/share/heteroes-local-acceptance/20261012-r2/acceptance.json` |
| Earlier archive | `~/.local/share/heteroes-session-archives/2026-10-11-monitoring-close-r2/`, independent encrypted copy on Archive |

Large writes on this workstation use Archive-2tb UUID `10443D1F443D094C`; verify
the actual mount before writing. Never use `/mnt/sekai`. This hardware UUID is
an operator constraint here, not a required filesystem for every future lab.
Live SQLite, runtimes and credentials remain on protected ext4. A previously
observed NTFS publication limitation led to a manifest-last immutable publication
fallback in the paused source; review its failure semantics before shipping it.

Do not print/copy private credentials, sudo passwords, signing keys, device tokens
or the earlier pasted Named Tunnel token into review artifacts. Cloudflared
2026.10.0 and a checksum-verified Caddy 2.11.7 are installed locally. No Named
Tunnel service token was used. A purchased domain is not configured deployment.

## 8. Why reconsider the cloud plan

The owner bought `heteroes.site` at Cloudflare and reports an AWS account with
approximately USD 100 credit. EC2 has not been provisioned. Originally the plan
targeted AWS CPU management, Cloudflare DNS/Named Tunnel and R2/S3 storage.
The owner now wants labs to avoid mandatory recurring hosting costs, vendor
dependence, external data placement and Internet control-plane availability.

Current temporary setup keeps CPU Web/API on the 5070 Ti workstation, exposes
small controls through Quick Tunnels, and uses LAN/Tailscale for large transfers.
Being on that workstation is an operational choice; it is not a coordinator
affinity constraint. AWS/R2/DNS/Named Tunnel are deferred and owner-operated.

Historical roadmap gates requiring cloud acceptance are superseded for the local
path. The domain may later serve documentation/downloads or an optional portal.
Cloud credit may test portability later; it should not define numerical architecture.

## 9. Three proposed deployment modes

| Mode | Intent | Important caveat |
| --- | --- | --- |
| A — Standalone Lab | Local management, GPU coordinator/workers, local metadata/weights; LAN and no Internet prerequisite after verified provisioning | Fresh offline install is not yet accepted; host availability still matters |
| B — Distributed Lab | Same local authority plus operator-selected HTTPS, reverse proxy, VPN or tunnel | Current temporary policy requires a private bulk path for initial/full fallback sync |
| C — Optional Hosted Portal | Optional shared account/metadata/monitoring service across labs | Future design only; tenant isolation and authority boundaries are unimplemented |

Distinguish three outage contracts: no Internet, no hosted portal, and no Local Lab
Server. They are different requirements. An accepted GPU run can make progress
through an observed management outage, but local relaunch/recovery while the lab
server is down is a broader claim requiring evidence and an explicit contract.

Ten labs may each self-host without ten rented VPSs. A future shared portal could
serve multiple labs; a GPU coordinator/ledger should remain lab-owned. The current
proposal recommends federation of local lab authorities. That choice still needs
review, especially how portal commands are locally accepted/rejected and how
stale projections or a duplicated controller are fenced.

## 10. Proposed architecture and alternatives to challenge

The previous assistant recommends retaining the existing independent CPU Local
Lab Server and management SQLite, using one local management authority, rather
than integrating management into the GPU coordinator or starting a new service.
Keep agent-owned lifecycle and direct worker-to-coordinator pull. Add verified
offline provisioning and qualify lifecycle/restore before optional federation.

| Choice | Current recommendation | Alternatives / reason to revisit |
| --- | --- | --- |
| Management process | Independent CPU service, optionally on the same workstation | Integrated launcher for smaller packaging; distinguish shared startup from shared correctness ownership |
| Management DB | Existing SQLite, one API authority for MVP | PostgreSQL if concrete concurrency, operational or future hosted requirements justify it |
| Compute ledger | Runtime-owned SQLite near canonical model | Do not move it to cloud just to centralize dashboards |
| Network | LAN-first, HTTPS/VPN/gateway adapters | Tunnels are optional; validate replay and full-sync reachability |
| Storage | Local filesystem/CAS first, S3-compatible optional | Do not make upload availability a prerequisite for a valid ES update |
| Packaging | Existing desktop/headless entrypoints first | CPU Docker Compose may help self-hosting later; not automatically a prerequisite |
| Initial hardware scope | One accepted experiment/coordinator first | Preserve explicit selection and existing parallel code; require real disjoint-job gate before claiming it |
| Future hosted portal | Federate local lab servers | Evaluate security, identity mapping and intent delivery before selecting final topology |

Proposed authority boundaries: management DB owns user intent/queue/assignments/
reservation epochs; training ledger and weights own numerical results/lineage;
agent/supervisor owns observed process existence and shutdown; management derives
product lifecycle from fenced evidence; a portal caches projections. Numerical
completion and resource release are separate facts. Silence proves neither death
nor permission to replace a running owner.

Existing routes include experiment create/edit/submit/cancel and agent-mode
pause/resume, `/api/v1/device/enroll`, `/api/v1/device/poll`,
`/api/v1/device/worker-command`, pairing/approval/contribution, idle endpoint
updates, qualification and resource/model/dataset queries. Compute uses `/v1/job`,
leases, heartbeats, results, failures, updates and verified model transfer.
These are observed interfaces; the proposal's future portal envelopes are not
implemented API routes. Inspect payload semantics and tests before designing
new contracts or asserting API-version compatibility.

## 11. Decisions still open for the owner

Claude should recommend an option for each, explain the trade-off, and indicate
which decisions block the next implementation slice:

1. Confirm process boundary: existing independent CPU Lab Server versus another
   launch/integration model. Avoid a rewrite without a concrete deficiency.
2. Confirm SQLite MVP scope and triggers for considering PostgreSQL.
3. Define offline acceptance: supplied offline bundle/local cache/LAN mirror,
   supported OS/runtime matrix, and first installation from an empty cache.
4. Define Local Lab Server outage behavior beyond already-executing computation:
   launch, preparation, generation boundaries, cancel, drain and recovery.
5. Define exact authority and observed states for RUNNING, FAILED, RECOVERING,
   COMPLETED and resource release. Do not invent failure from stale telemetry.
6. Confirm local worker enrollment and user/admin rules; decide whether existing
   pairing/self-test/approval/boot ON suffice for the first lab.
7. Define relocation versus intentional lab fork identity, controller fencing,
   credential/session rotation and reconciliation before unholding dispatch.
8. Define complete recovery closure: management DB, runtime ledger/weights,
   model/tokenizer files, datasets, selected checkpoints, configuration and private
   identity material. Hash references alone are not an offline restore payload.
9. Confirm desktop/headless-first versus an initial CPU Compose package, and the
   first native release gates. Containerization should solve deployment work.
10. Publish API/profile/recipe/ledger/management-schema/backup compatibility and
    supported upgrade/rollback combinations, including the additive v2 table.
11. Decide one-coordinator acceptance scope before real parallel independent jobs;
    do not remove the existing selectable-coordinator capability accidentally.
12. Defer or bound federation work; specify how local acceptance, tenant isolation,
    independent lab identity and cross-lab GPU ownership would be achieved.

The earlier handoff's eleven questions are also answered as recommendations in
the proposal. Those answers are not final architectural decisions.

## 12. Proposed implementation sequence after review

| Phase | Deliverable | Gate |
| --- | --- | --- |
| LF-0 — current review | Audit, evidence inventory, alternative analysis, proposed ADRs; owner decisions | Reconcile old handoff with actual dirty source; distinguish implemented/measured/proposed/pending |
| LF-1 — shipping baseline | Review preserved diff, resolve red checks, version/config contracts, CPU LAN startup | All required checks green; CPU host with GPUs hidden; same-origin UI; no required tunnel/cloud |
| LF-2 — Standalone MVP | Verified offline assets, one local coordinator/worker, v1 experiment and backup | Empty app cache/no outbound network; enroll/approve/ON; exact baseline; pause/resume; local artifact access |
| LF-3 — partition/relocation | Full lifecycle partition matrix and fresh-path held restore | No duplicate execution/release; correct epochs/lineage; previous controller stopped/fenced; complete offline inventory |
| LF-4 — Distributed Lab | Operator-selected network with verified control and bulk fallback | Auth, interrupted transfer/hash, replay/full-sync, rotation and an actual remote GPU run |
| LF-5 — expansion | Resume real M4 parallel and M5 model/data qualification | Disjoint physical GPUs; model-specific proof; v2 reproducibility and independent export reload |
| LF-6 — optional portal | Separate requirements/design when multiple labs need it | Tenant isolation, intent dedupe/local acceptance, stale projections, portal outage independence |

Each phase's detailed files/modules, dependencies, tests, acceptance and risks
are in the proposal. LF-1..3 is the recommended first reviewable MVP around the
pinned Qwen Recipe v1 profile. M5 source is preserved and parked; it does not
need to become an MVP prerequisite. Do not delete or quietly discard it.

Native Windows remains a release gate for Windows claims; inability to borrow
Windows/extra GPU hardware is a pending gate, not fixture-derived acceptance.
Quang's remote device is hard to borrow and Thao offers short windows. Linux
internal validation can progress separately. Historical GPU-hour caps were
removed, but explicit contribution, reservations and technical timeouts remain;
that old authorization does not resume GPU work during this architecture pause.

Project constraints: core/runtime freeze 2026-11-08, results freeze 2026-11-15,
submission 2026-11-20. Preserve evidence/report/demo deliverables. No architecture
acceptance depends on a positive held-out learning result or on spending AWS credit.

## 13. Expected output from Claude

Produce an independent technical review before code:

1. State exactly which source/commit/snapshot you inspected and what you could
   not access. Reclassify claims as code, measured, inferred, proposed or pending.
2. Challenge the three deployment modes and explain operational/trust assumptions.
3. Recommend the smallest local-first architecture, including module boundaries,
   state ownership, interfaces, persistence and failure behavior. Include alternatives.
4. Review each proposed ADR: retain/amend/reject, supporting evidence and open
   owner decision. Avoid silently changing its status to ACCEPTED.
5. Provide dependency-ordered tickets with scope/files, test plan, acceptance,
   risks and effort assumptions; identify the first small vertical slice.
6. Separate existing defects from architectural gaps, native acceptance gaps and
   future portal concerns. Preserve numerical and recovery invariants throughout.
7. Finish with a concise Vietnamese explanation of the decisions the owner needs
   to make. Do not implement until subsequent explicit authorization.

If using only this context rather than executable source, label your conclusions
as document-based review. Do not present a copied test count as a check you ran.
