# HeteroES-LLM — Architecture

> **Status:** draft v0.1, 2026-09-30 — written by Claude for review, not yet approved.
> **Audience:** the project team (A — Systems/Core, B — Product/Application).
> **Scope:** the big picture only. Exact numerical rules live in [numerical-contract.md](numerical-contract.md).
> **Sources of truth:** `HETEROES_LLM_MASTER.md` = what the system should be; `HETEROES_LLM_STATUS.md` = what is verified right now. If this file disagrees with them, they win.

## 1. Problem

A small lab owns a few consumer GPUs bought at different times: different VRAM, speed and architecture, connected by ordinary networks (same LAN, or Tailscale between sites). Several lab members want to share this pool to post-train a small LLM with Evolution Strategies (ES).

ES fits this setting:

- Each generation evaluates N perturbed copies of the model ("candidates") **independently** — candidates never talk to each other.
- Each candidate produces **one number** (a reward).
- Each worker holds a full copy of the model; we never split one model across GPUs.

The ES math is well known and is not our contribution. The hard part is making a distributed run **correct and measurable** on mismatched machines. The project is organized around four questions:

| ID | Question | Topic | Familiar analogy |
|---|---|---|---|
| C1 | Who may / should work? | Admission | Adding a server to a pool: "it can run the job" ≠ "adding it makes the pool faster" |
| C2 | Who gets which work? | Execution policy | Job dispatch / load balancing. Compared against known baselines, not claimed as new |
| C3 | Which result is valid? | Candidate / attempt / lease correctness | Idempotent payment processing: a retried request must not charge twice |
| C4 | Which model state is canonical? | Sync / replay | One source of truth + replicas that must stay consistent |

**Not goals:** a new ES algorithm, a new scheduling algorithm, public SaaS, billing, enterprise SSO, model sharding, untrusted volunteer compute.

## 2. One ES generation, end to end

Notation: θ_t = parent model weights at version t (494,032,768 numbers for Qwen2.5-0.5B). σ = noise scale (provisionally ~1e-3). N = candidates per generation.

```mermaid
sequenceDiagram
    participant C as Coordinator
    participant W as Worker
    C->>C: 1. pick N candidate seeds s_1..s_N
    C->>W: 2. candidate i (seed s_i, sigma, model version t)
    W->>W: 3. eps_i = NoiseEngine(s_i), about 494M Gaussian numbers
    W->>W: 4. perturb: theta = theta_t + sigma * eps_i
    W->>W: 5. run the prompt set, score it, get reward R_i
    W->>W: 6. restore theta_t exactly and verify
    W->>C: 7. reward R_i (a few bytes)
    C->>C: 8. standardize rewards into z_i
    C->>C: 9. regenerate eps_i = NoiseEngine(s_i) for every candidate
    C->>C: 10. theta_t+1 = theta_t + (alpha/N) * sum(z_i * eps_i), in FP32
    C->>C: 11. publish model version t+1
```

Steps 8–11 run on the coordinator or on a designated "update executor" machine (currently planned: the 5070 Ti).

### Why numerical reproducibility is a correctness problem here

The worker sends back **only R_i, never ε_i**. One ε_i in FP16 is ~1 GB (494,032,768 × 2 bytes), so shipping it is not practical. Instead the coordinator **regenerates** ε_i from the seed in step 9.

Step 10 pairs reward R_i with direction ε_i. If the coordinator's ε_i differs from the one the worker actually evaluated — even slightly — the update pushes the model in a direction that was never measured. **Nothing crashes. Training is silently wrong.**

So "same inputs → bit-identical noise on every machine" is not an optimization; it is the contract that makes distributed ES correct. Physical probes showed that native CUDA RNG (`torch.randn_like` on the GPU with the same seed) **breaks** this contract between the 5070 Ti and the 1660 Super, even with matched PyTorch/CUDA versions (STATUS §5). That is why the Numerical Core (section 5) exists and why it is built first.

Analogy: a client and a server that must independently compute the same hash of a request. If their implementations disagree, requests are silently mismatched.

## 3. System context

```mermaid
flowchart TD
    U["Researcher / lab member<br/>(browser, CLI)"]
    P["Product layer (B)<br/>login, workspaces, roles,<br/>experiment queue, dashboards"]
    C["Coordinator (A)<br/>generations, candidates, attempts,<br/>leases, ES update, model versions"]
    L[("Ledger")]
    A[("Artifacts<br/>checkpoints, manifests, events")]
    W1["Worker<br/>RTX 5070 Ti"]
    W2["Worker<br/>GTX 1660 Super"]

    U --> P
    P -->|"submit validated experiment config<br/>read run state / events"| C
    C --- L
    C --- A
    P -.->|read| A
    C <-->|"candidate, model version /<br/>reward, heartbeat"| W1
    C <-->|"candidate, model version /<br/>reward, heartbeat"| W2
```

Network: ordinary IP (LAN or Tailscale). SSH is for setup, debugging and administration only — never the runtime dispatch mechanism.

## 4. Major components

| Component | Responsibility | Owner | Exists today? |
|---|---|---|---|
| Product layer | Users, workspaces, roles (Admin/Researcher/Viewer), experiment metadata, non-preemptive experiment queue, dashboards, artifact browser | B | No (B starts from mock contracts) |
| Coordinator | Runs one experiment: admission (C1), candidate dispatch (C2), lease/result validation (C3), ES update, publishing model versions (C4) | A | No |
| Worker | Holds a model replica at an assigned version; perturb → evaluate → restore; reports reward + diagnostics. Has no optimizer of its own | A | No (logic exists only in the notebook and probes) |
| Numerical Core (`src/heteroes/`) | Library: ParameterSchema, CanonicalNoiseEngine, perturb/restore, reward standardization, ES update | A | ParameterSchema and CanonicalNoiseEngine v1 implemented and tested (03/10); perturb, restore, standardization, update not yet |
| Ledger | Durable record of candidates, attempts, leases, commits/rejections (planned: SQLite/WAL) | A | No |
| Artifact store | Checkpoints, manifests, events, regression evidence | A writes, B reads | Probe evidence only (`artifacts/probes/`) |

Two boundaries worth remembering:

- **The Numerical Core is a library imported by both Worker and Coordinator.** The worker uses it to create ε_i; the coordinator uses the *same code* to recreate ε_i. There must be exactly one implementation — two implementations that "should" agree is exactly how the CUDA RNG problem would come back.
- **Product queue ≠ candidate scheduler.** The product queue decides which *experiment* may start. Once an experiment runs, which *candidate* goes to which GPU is the coordinator's job. The product layer may display runtime state but never changes leases, commits or model versions.

## 5. Numerical Core — and why ParameterSchema comes first

The core is a chain of dependencies. Each layer can only be defined once the layer above it is fixed:

```mermaid
flowchart TD
    M["Model identity<br/>model id + pinned revision"]
    S["ParameterSchema<br/>which tensors are perturbable, in what canonical order?"]
    N["CanonicalNoiseEngine<br/>noise for (candidate, tensor k, chunk j)"]
    PR["Perturb / Restore<br/>(worker side)"]
    U["ES update<br/>(coordinator side)"]
    M --> S --> N
    N --> PR
    N --> U
```

### 5.1 ParameterSchema

The NoiseEngine does not receive a tensor. It receives an **address**: "candidate seed 42, parameter index 17, chunk 3". Two different machines must agree on what "parameter 17" means. ParameterSchema is that agreement: an ordered list of entries `(index, canonical_name, aliases, shape, dtype, numel)`, plus a hash of the whole list.

- **Analogy:** a database schema or an API contract version. If client and server disagree on the schema, you want a loud error, not silently reading the wrong column. The schema hash is part of the noise address, so a mismatch shows up as a detectable identity difference instead of silently wrong noise.
- **Tied (aliased) weights:** one tensor can be reachable under two names. In Qwen2.5-0.5B the probes found exactly one such group: `model.embed_tokens.weight` and `lm_head.weight` are the same tensor. The schema must list it **once**; otherwise the same memory would be perturbed twice and updated twice. This tensor alone holds 136,134,656 elements (~28% of the model).
- **Schema ≠ weights.** The schema describes the *shape* of the parameter space, not its values. A fine-tuned checkpoint has the same schema hash as the base model. Weight identity comes from model id + revision + model version.
- **No runtime addresses in identity.** `id(param)` or `data_ptr()` may be used inside one process to discover aliases, but are never stored or hashed — they change on every run.

### 5.2 CanonicalNoiseEngine

A pure, deterministic function:

```text
(schema hash, engine version, candidate seed, parameter index, chunk index, chunk size)
        → exact bytes of Gaussian noise for that chunk
```

v1 recipe (`numpy_pcg64_normal_f32_to_f16_v1`): SHA-256 of the address → seed a CPU NumPy PCG64 generator → standard normals in FP32 → cast to FP16. It runs on the CPU, so GPU architecture cannot influence it. A full-model probe produced byte-identical noise on both machines.

- **Why chunks:** each tensor is split into fixed-size chunks (262,144 elements in v1; 2,105 chunks for the whole model) and each chunk gets its own seed from its own address. Any chunk can be generated on its own, in any order, so worker and coordinator can process tensors in different orders or memory budgets and still get the same bytes. The chunk size is part of the contract: changing it changes the noise.
- **What must NOT affect the noise:** worker id, attempt id, lease, retry count, reward, workload, arrival time. A retry on a different GPU must rebuild exactly the same candidate.
- **Cost:** generating one full-model noise vector on CPU took 4.3 s on the 5070 Ti host and 18.1 s on the 1660S host in the probe (timing includes hashing). This is a real cost the design must account for; see ADR-001.

### 5.3 Perturb, restore, update (summary)

- **Perturb:** θ_t + σ·ε in the model dtype (FP16 for the current physical baseline).
- **Restore:** copy θ_t back from a snapshot and verify it is bit-identical. Not "subtract the noise again" — in floating point, (x + a) − a is not guaranteed to equal x.
- **Update:** accumulate Σ z_i·ε_i in FP32, cast to FP16 once, and check what was actually applied. Equal rewards → logged no-op. NaN/Inf reward → reject, never replace with 0.

## 6. Identity layers

Several kinds of "identity" exist; mixing them up is the most common source of confusion.

| Identity | Answers | Determined by | Must NOT depend on |
|---|---|---|---|
| Model | Which weights? | Model id + revision + model version t | — |
| Schema | What is the layout of the parameter space? | Names, order, shapes, dtypes, alias map | Weight values, memory addresses |
| Noise | Which exact Gaussian numbers for this chunk? | Schema hash, engine version, seed, parameter index, chunk index, chunk size | Worker, attempt, lease, retry, reward, workload, time |
| Candidate | Which logical ES candidate? | Parent model version, seed, noise recipe, σ, workload, generation config | Which worker ran it, how many retries |
| Attempt | Which execution try of a candidate? | Candidate + a new attempt id + lease | — (a new one on every retry) |

Note that σ is part of the **candidate**, not the **noise**: the same noise with a different σ is a different perturbed model.

**Candidate vs attempt** (the key C3 idea): a candidate is the logical job, like an order id; an attempt is one try at executing it. A retry keeps the same candidate (same seed, same noise, same workload) but gets a new attempt id and a new lease, possibly on another worker. The coordinator commits **at most one** result per candidate — duplicates and stale attempts are rejected.

## 7. State ownership

Rule of thumb: whoever owns a piece of state is the only one allowed to change it; everyone else reads a projection of it.

| State | Owner | Notes |
|---|---|---|
| Canonical model version | Coordinator / update executor | The only writer of weights. Workers never publish weights |
| Generation, candidate, attempt, lease, commit/reject | Coordinator + ledger | Correctness state. Never owned by the product layer |
| Worker capability / admission profile | Coordinator (measured on the worker) | |
| Worker model replica | Worker, at a version assigned by the coordinator | |
| Temporary perturbed weights | Worker | Exist only between perturb and restore; must return to θ_t exactly |
| Users, workspaces, roles, experiment metadata, experiment queue | Product layer | |
| Artifacts (checkpoints, manifests, events) | Coordinator writes; product indexes and reads | |

## 8. Current deployment

```mermaid
flowchart LR
    subgraph A["5070ti — RTX 5070 Ti, 16 GB, compute capability 12.0"]
        CO["Coordinator (planned)"]
        WA["Worker (planned)"]
    end
    subgraph B["heteroes-worker-1660s — GTX 1660 Super, 6 GB, compute capability 7.5"]
        WB["Worker (planned)"]
    end
    CO <-->|"LAN / Tailscale"| WB
    CO --- WA
```

- The 5070 Ti machine holds the primary repository and is where development happens. The 1660S runs **the same Git commit**; no separate development there.
- Traffic falls into two planes:
  - **Control plane** — small messages: candidate descriptors, leases, rewards, heartbeats. Needs reliability, not bandwidth.
  - **Data plane** — large payloads: model checkpoints (~1 GB in FP16), full synchronization. Network speed changes the *cost* here, never the *correctness*; C4 measures that cost.

## 9. Mapping to familiar architectures

If you know web development (MVC, REST, microservices), HeteroES has **two layers** that feel different:

- **The product layer is an ordinary web application.** MVC, REST API, a database of users and experiments — everything you already know applies.
- **The compute layer is a coordinator–worker system**, a different family from microservices. MVC answers "how do I organize code inside one app"; microservices answer "how do I split a large product into services by business area". Coordinator–worker answers "how do I split one heavy computation across many machines and combine the results correctly".

| HeteroES concept | Familiar equivalent |
|---|---|
| Generation | One batch job: split into N independent pieces, run them in parallel, then combine the results (the classic "map, then reduce" pattern) |
| Coordinator | A background-job scheduler plus its `jobs` table |
| Worker | A background-job worker or a CI runner: take a job, run it, report the result |
| Candidate | A logical job with a stable id, like an `order_id` |
| Attempt | One execution try of that job; a retry is a new attempt of the same job |
| Lease | A time-limited claim on a job ("visibility timeout" in message queues): if the worker goes silent, the job becomes available again |
| At most one committed result per candidate | Idempotent payments: a retried request must not charge twice |
| Ledger | A transactions table |
| Numerical Core | A shared library / SDK imported by several programs — not a service |
| ParameterSchema | A database schema or API contract version |

Four things make this system different from a typical web backend:

1. **Workers are stateful, heavy and unequal.** A stateless web service scales by adding identical instances behind a load balancer. Here every worker holds a ~1 GB model in GPU memory, and the workers are *not* identical (16 GB fast vs 6 GB slow). That is why C1 (should the slow machine join?) and C2 (how to split work?) exist.
2. **There is a synchronization barrier.** A web server handles each request independently. Here the update needs **all N** candidate rewards first, so one slow machine can delay the whole generation.
3. **Retries and network failures are normal.** This is the at-least-once delivery + idempotency problem found in payment systems and message queues. C3 must get it right.
4. **The same function can give different results on two machines.** In a web backend `1 + 1` is `2` everywhere. With floating point on different GPUs that is not guaranteed — the probes measured different noise from the same seed. Because the coordinator must recreate the noise the worker used, this is a correctness risk, not a performance detail. It is why the numerical contract comes before networking.

## 10. Why coordinator–worker (alternatives considered)

| Alternative | What it means | Why not the default here |
|---|---|---|
| **Peer-to-peer, no coordinator** | Every worker broadcasts its reward to every other worker and each one computes the update locally (the approach of the 2017 OpenAI ES paper) | No single referee decides which result is valid, so retries and failures (C3) become much harder; the weak 1660S must also compute every update; replicas can drift. The idea is not discarded: it is the **replay** mode that C4 will measure, with the coordinator still the source of truth |
| **An existing framework (Ray)** | Use Ray's task scheduling and retries; ES-at-Scale does this | Ray's retry means "run the task again"; it has no notion of candidate / attempt / lease and does not prevent a reward from being committed twice, so that logic must be written anyway. Running Ray across Tailscale between machines with different Python versions (3.12 vs 3.14) is added risk. MASTER keeps Ray as an ADR-gated option, not the default. This decision belongs after the numerical gate |
| **A job queue (Celery / Redis)** | Use an off-the-shelf queue for dispatch | Same issue: queues give at-least-once delivery, idempotency is still ours to build. Adds infrastructure to operate. MASTER: no Redis without a concrete need |
| **Asynchronous ES** | Do not wait for all N candidates; apply results as they arrive | Results computed on an older model version ("stale") complicate both the math and correctness. Kept as future work in MASTER |

**Known weakness of the chosen design:** the coordinator is a **single point of failure** — if it dies, the run stops. For a two-machine lab this is an accepted trade-off. Coordinator restart / recovery is a SUPPORTING item in MASTER, and the CLI must state clearly what is and is not recoverable.

**Bottom line:** the coordinator–worker shape is common and not a contribution. The value is in the **contracts** inside it: portable noise across GPUs, exactly-once candidate commits, and measured admission and synchronization decisions.

## 11. Current implementation boundary (updated 2026-10-05)

**Verified** (evidence in STATUS, `artifacts/probes/2026-09-29/` and `artifacts/regression/2026-10-03-o2-perturbation/`):

- Single-GPU ES reference (notebook) runs end-to-end on both GPUs in FP16.
- Exact snapshot restore (max diff 0.0) on both.
- Native CUDA RNG gives different noise across the two GPUs → rejected as the canonical noise source.
- NoiseEngine v1: identical noise bytes over the full model on the 5070 Ti, the 1660S, a Colab T4 and a Kaggle T4; package module with 117 tests.
- Perturbation arithmetic (O2 = option c, FP32 multiply then add, then cast): identical perturbed-weight hash on the same four environments (computed by a script; no package function yet).

**Done in order:** 1. ParameterSchema, 2. CanonicalNoiseEngine module, 3. unit / contract tests, 4. perturb and bitwise restore as package functions (05/10; checked on the 5070 Ti only; step 5, reward standardization and the FP32 update, was implemented on 05/10 evening; step 6, one candidate end to end, was run on the 5070 Ti on 05/10 night; both are checked on the 5070 Ti only).

**Next, in order:**

4. Route every perturb / reconstruct / update path through the one engine (perturb function first, then bitwise restore)
5. FP32 update accumulation + known notebook bugs
6. Local regression
7. Cross-machine same-candidate regression (5070 Ti vs 1660 S)
8. Freeze candidate / noise manifest v1

**Gate:** no networking, coordinator or ledger work until step 7 passes on both machines.

**Later:** worker/coordinator HTTP → one remote candidate → frozen two-node generation → SQLite ledger + leases → fault tests → C1/C2 experiments → full sync vs replay measurement.

## Glossary

| Term | Meaning |
|---|---|
| Generation | One ES step: evaluate N candidates, then produce model version t+1 |
| Candidate | One logical perturbation θ_t + σ·ε_i of the parent model |
| Attempt | One execution try of a candidate on a worker |
| Lease | Time-limited ownership of an attempt by a worker; expires if the worker goes silent |
| Seed | Integer that, with the schema and engine version, fully determines a candidate's noise |
| σ (sigma) | Noise scale: how far candidates move away from the parent |
| Chunk | Fixed-size slice of a parameter tensor; the unit of noise generation |
| Canonical | The single agreed-upon version of something (weights, noise bytes, schema) that all machines must match |
| Schema hash | Fingerprint of the parameter layout, used to detect layout mismatches |
| Full sync | Coordinator sends the whole new model to every worker after each generation |
| Replay | Workers rebuild θ_{t+1} locally from seeds + coefficients instead of downloading it |
