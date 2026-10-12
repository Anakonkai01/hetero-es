# ADR-004 — Local Lab Server, one supported control mode

Status: **PROPOSED**, with the owner decisions of 2026-10-12 recorded below as
DECIDED. Everything not marked DECIDED is still a proposal. This ADR does not
change ADR-001/002 or any numerical Recipe v1 contract.

Evidence labels: **[CODE]** exists in the inspected tree · **[MEASURED]** a dated
run recorded in evidence · **[PROPOSED]** recommendation · **[PENDING]** not yet
accepted by a test or run.

## Decision

1. **One Local Lab Server per lab.** A CPU-only FastAPI process with a management
   SQLite database. It serves the built Web UI and the API, owns users, the queue,
   assignments, epochs and physical-resource reservations. It never loads CUDA, model
   weights or the live training ledger. [CODE: `backend/` imports torch only inside
   `study/models.py:load()`, which no server module calls]
2. **Coordinator, workers and device agents stay separate processes.** They may share
   a host and a launcher with the Lab Server, but not databases or lifetimes.
3. **agent-v2 is the only supported control mode.** **DECIDED 2026-10-12 (D1).** The
   older loopback-gateway + SSH mode is frozen: kept in the tree to reproduce
   historical evidence, labelled unsupported, excluded from the test matrix.
   [CODE: a database created in agent mode refuses the legacy dispatcher,
   `store.py:52-54`]
4. **SQLite, one API process, for the MVP.** **DECIDED 2026-10-12 (D2).** Revisit
   PostgreSQL only if one of these happens (thresholds are suggestions, not
   measurements): more than one API process is required; p95 of `device/poll` stays
   above ~250 ms with the real number of agents; the database reaches several GB; a
   hosted multi-lab service is built.
5. **A, B, C are configurations of the same program, not three products.** A
   configuration is: bind/advertised addresses, transport security level, storage
   adapter.

   | Config | What it is | Status |
   |---|---|---|
   | **A — Standalone** | LAN only. Numeric private IP, **fixed or DHCP-reserved** (documented prerequisite). Plain HTTP on the LAN with a `doctor` warning. Offline = a pre-seeded, hash-verified cache (USB or folder). **DECIDED (D3).** | acceptance [PENDING] |
   | **B — Distributed** | A plus an operator-chosen route: an encrypted overlay (WireGuard, Tailscale, Headscale) or an HTTPS hostname with a private bulk route. Large files need a private route only when the chosen ingress cannot carry them; this is a property of the ingress, not a rule of the architecture. | acceptance [PENDING] |
   | **C — Hosted portal** | Deferred. If ever built, labs push **read-only** snapshots out; the portal never sends commands to a lab. | not designed |

6. **One launch path.** `python -m backend.server --headless` plus a systemd unit
   template for LAN use. `deploy/install-cpu-server.sh` (needs a domain) and
   `scripts/local-lab.py` (Quick Tunnel) become documented adapters for config B.
7. **Easy deployment is a requirement. DECIDED 2026-10-12 (D8).** Each role has a
   guided installer flow, on Linux and Windows where the role is qualified:

   | Role | Linux | Windows | Today |
   |---|---|---|---|
   | **Lab Server** (CPU) | target, desktop app exists, clean install seen under Xvfb | target "if time"; installer exists, native acceptance [PENDING] | [CODE] `desktop/server` |
   | **Worker** (GPU) | target; app exists | target; `.exe` exists (unsigned), Recipe v1 trial on an RTX 3060 on 2026-10-11 [MEASURED] | [CODE] `desktop/worker` |
   | **Coordinator** (GPU, ≥ 11 GB VRAM) | target: a **toggle inside the Linux app** | **not supported** (numerical qualification is Recipe v1 worker-only) | [CODE] gap: the app enrolls every device with `workerOnly: true` and `coordinator: false`; a coordinator is a manual command-line setup |

   Three further parts of the same requirement [PROPOSED, tickets E1–E3]:
   - **E1** the coordinator toggle: shown only when the device self-test says
     coordinator-capable; it fills the listening address from the network the user
     chose (today the agent listens on `127.0.0.1`, which remote workers cannot reach).
   - **E2** a network choice in the Lab Server and Worker apps with a
     "check connection" step (see ADR-006).
   - **E3** one page of instructions per role.

   Compose, Kubernetes, mandatory PostgreSQL, hosted authentication and
   provider-specific queues are out of scope.

## Why a separate process (the honest reason)

On one workstation a separate Lab Server does **not** improve availability: if the
machine is off, both are off. The reasons are lifetime isolation (a Web restart
must not touch a running GPU job) and keeping the frozen numerical core free of
product code. On a separate always-on CPU host it also improves availability, using
the same contracts.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Management inside the coordinator process | Ties Web lifetime to a GPU process; the coordinator device changes per experiment, so "where is the lab" becomes ambiguous |
| Mandatory hosted management | Puts WAN and an account service into every lab |
| Portal that replaces local management | Needs a second command authority and reconciliation |
| PostgreSQL now | Adds a service to run and back up with no measured need |

## Acceptance

Mode A is accepted by one run with no outbound network, from an empty cache: install,
enroll, approve, turn ON, a Recipe v1 job, pause/resume with the baseline hash,
artifact access, and restore onto a fresh path. [PENDING — ticket LF-2]

## Still open

First OS matrix beyond Linux; whether to ship a CPU container recipe after the
headless path is accepted. Neither changes the ownership rules in ADR-005.
