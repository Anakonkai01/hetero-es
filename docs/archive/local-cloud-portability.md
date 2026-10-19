# Local completion and deployment portability

> **Paused by later owner instruction, 2026-10-12:** the implementation scope below
> was authorized before the architecture review request. Preserve its working-tree
> changes and evidence, but do not continue coding automatically. The current
> [audit/proposal](local-first-architecture.md) and
> [Claude handoff](local-first-claude-handoff.md) define the review task. Their
> detailed technical recommendations require owner decisions.

Owner-approved implementation specification, 2026-10-12. Cloud provisioning,
DNS changes, Named Tunnels and R2 activation remain owner-operated and deferred.
No push, merge or tag is part of this implementation.

The CPU Web/API serves built static assets and uses one origin. Each experiment
selects its qualified coordinator; neither the CPU service nor coordinator
selection depends on the 5070 Ti. Bind addresses, public Web, public compute and
private bulk addresses are separate configuration fields. Quick Tunnels expose
only small control requests. Models, checkpoint payloads and installers require
LAN/Tailscale. Existing identities, histories, numerical Recipe v1 and hashes
must survive address changes. Reconfiguration requires OFF and confirmed drain.

## Dependency-ordered acceptance tickets

| Ticket | Deliverable | Acceptance |
| --- | --- | --- |
| 1 | CPU headless service, endpoint contract, owned Quick helpers, provider-neutral release/config | Same-origin built UI; TLS control/private bulk; denied public bulk; stale-PID fencing; URL rotation preserves identity |
| 2 / M3 | Linux portable leased candidate, replay, reference, lifecycle/outage; dated installer manifests | Compare predictions/rewards/child weights; restart OFF; drain before release; user Linux and native Windows walkthrough |
| 3 / M4 | GPU boundary pause/resume and disjoint scheduling | Resumed final weights match uninterrupted; one physical UUID cannot double-book; separate real GPUs gate parallel acceptance |
| 4 / M5 | Pinned model registry, mapped data/splits, Recipe v2, batches/sigma, evaluation/export | Preserve v1 goldens; deterministic resume; validation-only selection and locked test; independent export reload |
| 5 / M6 | Faults, migration/restore/rollback, fresh install/operator demo | Auth/epoch fencing; interrupted transfer; changed endpoints; integrity-checked snapshot; repeatable demo |

Tests and evidence distinguish implementation from real hardware acceptance.
Unavailable Windows or extra GPU hardware is an open acceptance gate, never
inferred from CPU mocks. Large files require the verified Archive-2tb UUID
10443D1F443D094C; missing mount must fail before creating directories.
