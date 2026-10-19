# M2 implementation record

> **Historical record:** measured M2 behavior below is retained. As of 2026-10-12,
> cloud is optional/deferred and is not a local release prerequisite. This record
> does not prove a full offline install, all lifecycle partitions or simultaneous
> disjoint jobs. See the current [audit/proposal](local-first-architecture.md).

Status: local implementation verified; cloud acceptance pending, 2026-10-10. The accepted scope and gates are in
[lab-roadmap.md](lab-roadmap.md). Local implementation is not cloud acceptance.

## Preserved baseline

Track A `a084418`, Track B `a3e39db`. New M2 branches preserve the M1 branches,
research worktree, historical experiment IDs and evidence. The local admin
password remains unchanged. The full M1 backup remains private and local.

## Delivered

The CPU backend has an explicit `agent` deployment mode and no CUDA/Track A
dependency. Existing accounts, workspace history and FIFO are preserved. Three
real devices passed compatibility tests and were enrolled/approved in an isolated
copy of the M1 product. Owners explicitly enable each new agent boot; all boots
start OFF. The CLI agent accepts typed commands and owns only its recorded child
processes. Experiment dispatch uses outbound HTTPS/HTTP polling rather than SSH.
SSH was used only to install/update the isolated source and operate this campaign.

Assignments reserve the coordinator and every selected worker atomically, even
when the coordinator is not a candidate worker. Run/assignment/epoch checks and
individual run credentials bind each worker alias and attempt to its authenticated
identity. Offline heartbeat is a display status, never release or failover authority.
Cancellation drains; every selected process must be confirmed dead before release.
Unknown process identities keep ownership held. Persistent quarantine, revocation,
boot resets, duplicate agents, late commands and stale reports have CPU tests.
Revoked coordinators retain only scoped poll/stop access for their unreleased
assignments so cancellation can finish draining workers; this access ends at release.

The coordinator captures a consistent SQLite backup at published-generation
boundaries with the required parent/child weights, frozen config and pinned
recipe/code/environment identity. K/N defaults are 1/3; changes take effect at
the next generation, and a final point is always captured. Recipe v1 and numerical
semantics are unchanged. Restore verifies full hashes, sizes, ledger integrity
and canonical lineage; it publishes into a new held directory without old PIDs.
New points fingerprint every runtime Python source file, including isolated
coordinators without Git metadata. Exported legacy M1 points preserve their original
recorded provenance; they do not claim this later source fingerprint retroactively.

The S3-compatible R2 adapter issues scoped, expiring multipart/single upload and
download rights. Master credentials stay on the CPU host. Uploads go to temporary
keys, are read back and fully hashed, then conditionally copied into canonical
content-addressed keys. The manifest is published last. Refcounts, retention,
pending-upload cleanup, an 8 GB quota including upload/copy reservations, an 80%
warning and conservative monthly request caps are implemented. Cloud errors keep
compute running with local pending points. Metadata uses consistent hourly backups,
up to 24 within quota. Cloud adapter tests use memory objects and SDK stubs;
they are not real R2 evidence. Live worker weight/replay traffic still uses the
private coordinator compute endpoint.

The dashboard supports pairing, approval/revocation, boot contribution, explicit
coordinator selection, backup policy and sync status. Monitoring events spool
durably and deduplicate after outages. Large heartbeat projections are bounded,
with truthful total counters and a recent-history indicator; canonical ledger
and complete event history are retained. Small verified artifacts are cached on the
CPU server. Ready cloud checkpoints have revocable native download tickets.
Deployment scripts prepare an independent admin, check live AWS Free Plan gates,
build a credential-free CPU release and install one backend process plus Caddy
on a fresh Ubuntu CPU server. Fixed DuckDNS management HTTPS is the selected M2
route; compute remains private Tailscale. Named tunnels/installers remain M3.

## Verification

- Track A: **2,162 passed, 21 skipped**. Track B: **72 passed**.
- Frontend production build/lint and **22 mock behavior groups** pass. Mock
  evidence is separate from the real runtime campaign.
- Scratch mutations disabling worker identity and assignment epoch checks both
  turned the corresponding tests red without changing either checkout.
- Real browser: three devices, approval controls, coordinator selection, K=1/N=3,
  no JavaScript errors. CPU-cached config download works with compute stopped.
- Migration imported **16** original experiments with exact bodies/FIFO preserved,
  sessions revoked, a separate admin and a held queue. After the campaign, a real
  local metadata restore preserved all **19** experiments, FIFO and reservations;
  fresh API login and cached artifact download passed with zero GPU launches.
- Three-GPU run `d09d6ea8ac904cc7be92fa833637abde`: N=12/G=3, `arith16`,
  `hf_generate`, FP32 evaluation, CPU canonical noise, alpha=sigma=0.001.
  5070 Ti committed **20**, Quang's 3060 **6**, Thao's 3060 **10** candidates.
  All three generations completed and all selected processes stopped.
- Its final SHA-256 exactly matches a single-GPU baseline using the same run ID
  and numerical configuration:
  `9947f34c5b6e08667a4283d23d7021dcbb685fb536d10c2e4d85cda420aba7af`.
- During run `60346847f48f4d77a2e51c8885bff178`, the actual staging API was
  unavailable for an observed **40.055 seconds**. Generations 1 and 2 finished
  during the outage; compute continued, metadata/events synchronized after API
  restart, and reservations were released only after confirmed shutdown.
- A five-file final recovery point restored locally into a fresh held directory
  with the same checksum. The selected M1 checkpoint
  `096b09ec03ab4d8b9ca189596593db3a` was also exported/fully verified for cloud
  import; its SHA remains
  `987541249378460c668ff9865cbcc5823331eddae4bdfbebd87a532977b96c38`.

After the hardware campaign, optional backup-policy corruption/write failures,
large monitoring projections, exact source fingerprints and revoked-coordinator
draining were regression tested on CPU. These refinements
were not another GPU campaign; the real cloud acceptance remains required.

The first three-GPU start `a431cce322444bd2b397b73d0c4df67c` was cancelled after
worker argument and command-transaction bugs. Both were corrected and regression
tested. Its full reservation interval is included in the budget, not discarded.
M2 consumed **0.416201 of 0.5 GPU-hours**, including a 0.01 GPU-hour self-test and
diagnostic allowance. Including M1, **1.021832 of the original 2 GPU-hours** were
used. No further GPU campaign ran after this accounting.

Sanitized evidence:
[`2026-10-10-m2-agent-cloud`](../../hetero-es-integration/artifacts/experiments/2026-10-10-m2-agent-cloud/).
Raw logs, screenshots, tokens, databases and weights remain outside Git.

## Current operation

M1 dispatch and runtime maintenance have been restored. Its private UI remains
on port 5173 with the existing local credentials. M2's isolated CPU review UI is
on port 5175, its queue is held and all three M2 agents are OFF/stopped. Do not
enable two controllers on the same physical GPUs. The full 33.6 GB M1 backup and
old evidence remain local and unchanged.

## External prerequisites

The owner explicitly confirmed that cloud accounts have not been created.
AWS Free Plan eligibility/remaining credits, Cloudflare R2 account access and
DuckDNS account/address are not yet available to the implementation session.
Credentials must be supplied through private local files or provider login,
never committed or sent in chat. Paid-plan upgrade is outside the accepted scope.
Read-only preflight reports zero provisioned resources. No AWS instance, R2 bucket,
DNS update or public endpoint was created. **M2 remains incomplete** until real R2
upload/download/restore and the actual EC2 HTTPS/browser acceptance pass. Provisioning
and the Ubuntu installer are prepared and syntax checked, not deployed evidence.

Next: follow [m2-cloud-operator.md](m2-cloud-operator.md) to create the accounts,
configure private credentials, verify free-plan/billing gates, test the selected
M1 point on R2 and perform an idle cloud cutover. Preserve the remaining M2 GPU
budget for the short cloud-backed acceptance; do not start M3 as if M2 had passed.
