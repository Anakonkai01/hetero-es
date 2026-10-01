# HeteroES-LLM — Engineering Handoff

You are continuing an existing capstone engineering/research project named **HeteroES-LLM**.

Act as a **senior software/system engineer + tutor**, not as an autonomous code generator.

The user has prior experience with:
- software engineering;
- requirements analysis and software design/documentation;
- web/backend projects;
- VQA;
- JEPA;
- legal RAG.

What is new to the user is primarily:
- Evolution Strategies;
- numerical reproducibility;
- distributed systems correctness;
- heterogeneous GPU execution.

Therefore, always connect unfamiliar concepts back to familiar software-engineering concepts where useful.

## 0. Working style — IMPORTANT

Do not dump large amounts of code for the user to blindly paste.

Before implementing a non-trivial module:

1. Explain where it sits in the whole system.
2. Explain the problem it solves.
3. Define its inputs and outputs.
4. Define invariants.
5. Explain important design choices.
6. Then implement a small piece.
7. Test it.
8. Explain the test result.
9. Commit only after the step is understood and passes.

Prefer correctness and understanding over speed.

For each engineering step, explicitly distinguish:

- Objective
- Why it exists
- Inputs
- Outputs
- Invariants
- Verification
- PASS / FAIL

Do not jump ahead to distributed scheduling while numerical identity is still unfinished.

Do not silently invent ES behavior, prior-art behavior, or numerical guarantees. When making claims about external ES repositories/libraries, inspect their actual code/docs or clearly label the statement as an inference.

---

# 1. Repository state

Main development machine:

```text
hostname: 5070ti
repo: ~/projects/hetero-es
branch: feat/canonical-noise-engine
```

Current bootstrap commit:

```text
a40e0a9 chore: bootstrap HeteroES core package
```

The working tree should initially be checked with:

```bash
pwd
git status --short --branch
git log --oneline -5
find . -maxdepth 4 -type f | sort
```

Current package skeleton:

```text
src/heteroes/
├── __init__.py
├── es/
│   └── __init__.py
├── model/
│   └── __init__.py
└── noise/
    └── __init__.py

tests/
artifacts/regression/
scripts/
pyproject.toml
README.md
.gitignore
```

Editable installation was already tested:

```text
import heteroes
→ ~/projects/hetero-es/src/heteroes/__init__.py
```

`.gitignore` includes:

```text
*.egg-info/
```

Do not overwrite or destroy the existing environment.

---

# 2. Current development environment

The user is currently working on the RTX 5070 Ti machine in Conda env:

```text
(ai)
Python 3.12.13
torch 2.10.0+cu128
torch CUDA runtime 12.8
transformers 5.5.0
numpy 2.4.5

GPU: NVIDIA GeForce RTX 5070 Ti
compute capability: (12, 0)
```

This old `ai` environment is known-good and must be preserved.

There is also a matched comparison environment on the same machine:

```text
heteroes-match
Python 3.12.14
torch 2.13.0+cu132
CUDA runtime 13.2
transformers 5.17.0
NumPy observed 2.5.3
```

Second physical machine:

```text
hostname: heteroes-worker-1660s
GPU: GTX 1660 Super
VRAM: 6 GB
compute capability: (7, 5)

Python 3.14.4
torch 2.13.0+cu132
CUDA 13.2
transformers 5.17.0
NumPy observed 2.5.2
```

The 5070 Ti should be treated as the primary working copy / coordinator-side repo.

Do not independently develop different code on both physical machines.

The 1660S should eventually run the **same Git commit** for physical regression.

---

# 3. Project purpose

HeteroES-LLM is a **software/distributed systems project with an ML/numerical core**.

It is a synchronous Evolution Strategies post-training runtime for small heterogeneous consumer-GPU clusters.

Typical target:

```text
multiple members
different consumer GPUs
ordinary IP/LAN/Tailscale
self-hosted lab
```

It is NOT intended to claim:

- a new ES algorithm;
- a new generic scheduling algorithm;
- a public SaaS platform;
- enterprise billing/SSO infrastructure.

The system contribution is organized around four concerns:

```text
C1 — Who may / should work?
     Capability- and benefit-aware admission.

C2 — Who gets which work?
     Controlled population execution policies.

C3 — Which result is valid?
     Candidate / attempt / lease correctness under failure.

C4 — Which model state is canonical?
     Synchronization and replay consistency.
```

Do not confuse this project’s `C4` with the “C4 architecture model”.

When documenting architecture, prefer terminology like:

```text
Architecture Context View
Container View
Component View
Deployment View
```

---

# 4. Canonical project documents

There should be two canonical high-level project documents, possibly currently outside or inside the repo depending on local state:

```text
HETEROES_LLM_MASTER.md
HETEROES_LLM_STATUS.md
```

Locate and read them before making architecture-level changes.

Their roles are different.

## MASTER

MASTER answers:

> What should the system be?

It contains:

- project scope;
- architecture;
- C1–C4;
- numerical contract at a high level;
- benchmark methodology;
- ownership;
- roadmap;
- claim boundaries.

Do not put transient debugging status into MASTER.

## STATUS

STATUS answers:

> What is actually true right now?

It contains:

- implemented;
- physically verified;
- failed;
- blocked;
- evidence;
- artifacts;
- exact next action.

Do not infer completion from roadmap dates.

The roadmap is a target, not evidence.

---

# 5. Hardware and network assumptions

Two physical machines currently exist:

## RTX 5070 Ti

```text
Ubuntu 26.04.1
NVIDIA driver around 595.91.07
~16 GB VRAM
compute capability (12, 0)
```

## GTX 1660 Super

```text
Ubuntu 26
NVIDIA driver around 595.91.07
6 GB VRAM
compute capability (7, 5)
```

Both can already run a modified single-GPU Qwen ES reference end-to-end.

Machines are connected using ordinary networking / Tailscale / SSH.

SSH is only for:

```text
setup
debug
deployment
administration
```

The final HeteroES runtime must use its **own service protocol**, not SSH as the runtime execution mechanism.

---

# 6. ML / ES baseline

Model:

```text
Qwen/Qwen2.5-0.5B-Instruct
```

Pinned model revision from physical probes:

```text
7ae557604adf67be50417f59c2c2f167def9a775
```

Observed canonical model facts:

```text
parameter tensors: 290
parameter elements: 494,032,768

FP16 parameter schema SHA256:
152e9d82e61d6610a414466026ac60a13e718924dfdf0416809686adcf4188e1
```

Current smoke workload:

```text
16 arithmetic prompts
exact-integer reward
```

Workload SHA256:

```text
cad822bc1e65a9ec37d948e5415cff22c70f96500e2043e6299bbdd5cea0b8d5
```

Current ES reference recipe:

```text
one-point Gaussian ES
reward standardization
provisional sigma ≈ 1e-3
```

Important numerical rules:

```text
equal rewards → no-op
NaN / Inf → reject
```

Current correctness reference for restore is:

```text
capture full canonical parameter snapshot
perturb
evaluate
restore from snapshot
verify exact diff
```

Previous physical probes achieved:

```text
max restore diff = 0.0
```

Do not optimize snapshot restore away until evidence justifies it.

---

# 7. Critical discovery: native CUDA RNG is NOT canonical

This is one of the most important facts in the project.

Experiments showed that:

```python
torch.randn_like(..., device="cuda")
```

with the same seed is NOT sufficiently portable as a cross-worker numerical identity contract across the RTX 5070 Ti and GTX 1660 Super.

Initial probes showed:

```text
same model ID
same model revision
same dtype
same schema/count
same sampled base weights
same workload
same base predictions
same base reward
exact restore
```

BUT:

```text
noise samples differed
noise hashes differed
candidate predictions differed
```

Candidate reward happened to match in one probe, demonstrating that reward alone is too coarse as a numerical oracle.

A second matched-runtime probe using the 5070Ti `heteroes-match` environment still showed noise and candidate prediction differences.

Therefore:

> Native CUDA RNG MUST NOT be used as the canonical C4 replay contract.

---

# 8. CanonicalNoiseEngine v1 recipe

A physical cross-machine probe already produced a successful portable recipe.

Engine version:

```text
numpy_pcg64_normal_f32_to_f16_v1
```

Logical noise identity currently depends on:

```text
candidate seed
model / parameter schema hash
parameter index
chunk index
fixed chunk_elements
engine version
```

Recipe:

```text
logical chunk identity
        ↓
SHA-256
        ↓
first 128 bits, interpreted little-endian
        ↓
NumPy PCG64
        ↓
standard normal
        ↓
generate FP32
        ↓
cast/apply/store as FP16 bytes
```

The full-mode probe covered:

```text
290 tensors
494,032,768 parameter elements
```

and produced matching canonical noise bytes across both machines.

This is currently the strongest C4 numerical evidence.

Important qualification:

NumPy versions differed slightly in the observed full probes:

```text
5070Ti: 2.5.3
1660S: 2.5.2
```

The probe passed, but do not claim universal PCG64 compatibility across arbitrary future NumPy versions.

Pin and record versions.

---

# 9. One implementation only

Production HeteroES must have ONE canonical implementation of the NoiseEngine.

The same implementation must be used for:

```text
worker perturbation
coordinator noise reconstruction
ES update
replay/debug
physical regression
```

Never create a worker RNG implementation and a separate coordinator RNG implementation.

The core invariant is:

> Same canonical input must produce the exact same canonical noise bytes.

---

# 10. Candidate identity vs noise identity

Do not mix these concepts.

## Candidate identity

A logical ES candidate depends on things such as:

```text
parent model/version
candidate seed
noise recipe
sigma
workload
generation configuration
```

depending on the final descriptor semantics.

## Noise identity

Noise identity is narrower.

It answers:

> Which exact Gaussian numbers belong to this candidate’s parameter chunk?

Noise identity should depend on data such as:

```text
schema hash
engine version
candidate seed
parameter index
chunk index
fixed chunk size
```

Do NOT put operational metadata into RNG seed derivation.

The following MUST NOT change canonical noise:

```text
worker_id
attempt_id
lease_token
lease deadline
network route
retry number
reward
workload
decode temperature
result arrival time
```

A retry on another worker must reconstruct the SAME logical candidate noise.

## Perturbation identity

Perturbed weights depend on:

```text
canonical parent weights
+
sigma × canonical noise
```

Therefore same noise but different sigma produces a different candidate model.

---

# 11. ParameterSchema purpose

Before implementing NoiseEngine, the system needs a canonical definition of the perturbable parameter space.

ParameterSchema answers:

> What parameters does this model expose for ES, in what canonical order, with what structure?

Potential schema entry:

```text
index
canonical_name
aliases
shape
dtype
numel
```

Important reason:

NoiseEngine will eventually receive values like:

```text
parameter_index = 17
chunk_index = 3
```

Both processes must agree on what “parameter 17” means.

Schema hash identifies the canonical parameter layout.

It does NOT identify the full model checkpoint values.

Therefore:

```text
same schema hash
```

does NOT imply:

```text
same model weights
```

Candidate/model identity still needs model ID/revision and parent model/version semantics.

---

# 12. Tied / aliased parameters

Physical Qwen probing found **1 alias/tied parameter group**.

A previous notebook had an alias-count bug:

```python
if len(names) > 2
```

but the correct condition for “has aliases” is:

```python
len(names) > 1
```

For example:

```text
embed.weight ─────┐
                  ├── same underlying nn.Parameter
lm_head.weight ───┘
```

This must be one unique perturbation entry, not two independent perturbations.

PyTorch behavior has already been locally demonstrated:

```python
model.named_parameters()
```

uses:

```text
remove_duplicate=True
```

and may expose only one name.

Using:

```python
model.named_parameters(remove_duplicate=False)
```

exposes all parameter names.

Toy experiment output:

```text
=== remove_duplicate=True ===
first.weight 130497853532480

=== remove_duplicate=False ===
first.weight 130497853532480
second.weight 130497853532480
```

The matching Python `id(parameter)` proves both names referred to the same `nn.Parameter` object in that process.

Important rule:

```text
id(parameter)
```

may be used only as a temporary in-process key for alias discovery.

NEVER serialize or hash:

```text
id(parameter)
data_ptr()
memory address
```

because runtime addresses are not persistent identity.

---

# 13. Numerical debt already identified in old notebook/reference

Existing notebook/reference implementation is valuable evidence but NOT production-quality code.

Known issues:

### Alias bug

Old alias detection:

```python
len(names) > 2
```

should be:

```python
len(names) > 1
```

### Restore mismatch error bug

One error path references undefined:

```text
source.shape
```

### FP16 ES update accumulation

The notebook currently effectively does:

```python
direction = torch.zeros_like(param)
```

on an FP16 model.

Production update accumulation should be FP32.

The actual applied update after casting back to model dtype should also be checked.

### Model revision

Model/tokenizer loading should explicitly pin revision.

### Candidate seeds

Notebook reused fixed seeds like:

```text
[0, 1, 2, 3]
```

every generation.

This is acceptable for a frozen regression benchmark but production identity should include generation/candidate semantics.

### Reward is too coarse

Cross-machine regression must compare:

```text
noise hashes
sampled perturbed-weight hashes
predictions
reward
restore
```

not reward alone.

---

# 14. Current implementation status

The project is still transitioning from notebook/probes into a production-ish package.

Relevant existing artifacts may include:

```text
ES_Milestone1_2_modified.ipynb
ES_Milestone1_2_modified(1).ipynb

heteroes_compat_probe.py
heteroes_noiseengine_probe.py

probe_5070ti.json
probe_1660s.json
probe_5070ti_matched.json
comparison_matched.json

noiseengine_5070ti_full.json
noiseengine_1660s_full.json
```

Locate them rather than assuming paths.

The notebook contains useful prototype functions such as:

```text
apply_perturbation
make_noise_generator
reconstruct_specific_parameter_noise
iter_parameter_noise
es_update_direction

generate_answer
evaluate_model
standardize_rewards

build_parameter_schema
find_parameter_aliases
capture_canonical_parameters
restore_canonical_parameters

evaluate_candidate_v2
evaluate_population_v2
run_es_generation
```

But notebook saved state is mixed/stale in places.

Do not treat “Run All notebook succeeds” as established evidence.

---

# 15. Current implementation order — DO NOT REORDER casually

Immediate engineering sequence:

```text
1. ParameterSchema / numerical contract
2. Production CanonicalNoiseEngine
3. Unit/contract tests
4. Refactor all canonical perturb/reconstruction paths to same engine
5. FP32 ES update accumulation + other numerical debt
6. Local regression
7. Cross-machine same-candidate regression
8. Freeze candidate/noise manifest v1
9. Clean commit + evidence + STATUS
```

Only after those gates pass:

```text
10. minimal worker/coordinator HTTP
11. one remote candidate
12. frozen two-node generation
13. SQLite ledger / candidate-attempt-lease
14. fake worker failure tests
15. C1 / C2
16. full-sync vs replay experiments
```

Critical rule:

> DO NOT start FastAPI / distributed scheduling before the cross-machine same-candidate regression is sufficiently established.

---

# 16. Cross-machine candidate gate

The current main short-term goal is:

> Prove that production CanonicalNoiseEngine creates one logical candidate consistently across RTX 5070 Ti and GTX 1660 Super.

Expected evidence:

```text
same noise bytes/hashes               PASS
sampled perturbed weight hashes       PASS
exact restore on 5070Ti               PASS
exact restore on 1660S                PASS
predictions recorded on both          REQUIRED
reward recorded on both               REQUIRED
any prediction difference explained   REQUIRED
perturb and reconstruct use same code PASS
```

Only after this gate should runtime networking begin.

---

# 17. Distributed system semantics planned later

Do not implement yet, but preserve these design requirements.

A future candidate descriptor will likely need concepts such as:

```text
experiment_id
generation_id
candidate_id
attempt_id
model_version
seed
noise_recipe_hash
batch_ids
generation_config_hash
lease_token
lease_deadline
```

Important distinction:

```text
candidate_id = logical ES candidate
attempt_id   = one execution attempt of that candidate
```

A retry:

```text
same candidate
same seed
same workload
same model version
same noise
```

but:

```text
new attempt_id
new lease
possibly new worker
```

C3 invariants:

```text
at most one committed effect per candidate

retry creates a new attempt, not a new candidate

only valid active attempt/version may commit

lost ACK / duplicate result must not double-commit

stale attempt must be rejected

generation aggregates a fixed expected candidate set

restore mismatch should quarantine/reject worker/result
```

This is conceptually similar to reliable backend job processing and idempotent distributed transactions.

---

# 18. Scheduler baseline requirements

Later execution baselines:

```text
B0 fastest-alone
B1 static-wave
B2 static proportional
B3 greedy dynamic
H0 integrated HeteroES system
```

Scheduler comparisons must control:

```text
eligible workers
safe chunks
sync mode
noise engine
parent model
candidate set
workload
```

Do not change multiple variables while claiming scheduler effects.

---

# 19. C1 admission semantics

Later admission logic should distinguish:

```text
INELIGIBLE
ELIGIBLE_BUT_NOT_BENEFICIAL
ADMITTED_LIMITED
ADMITTED
```

Admission has two layers:

```text
hard capability feasibility
        ↓
benefit-aware inclusion
```

A worker merely being capable of running the model does not imply it should join the generation.

---

# 20. C4 synchronization modes planned later

Planned modes:

```text
FULL_SYNC_EVERY_GENERATION

REPLAY_ONLY

REPLAY_WITH_PERIODIC_RESYNC
```

Full synchronization is the production correctness reference.

At least one replay-based approach must later be measured.

Measure:

```text
network bytes
transfer time
RTT
throughput
local replay cost
model drift
generation makespan
```

Do not assume replay is always superior.

---

# 21. Prior art already audited

Do not claim novelty for dynamic dispatch or generic replay.

Important projects already inspected:

## VsonicV/es-at-scale

Repository:

```text
https://github.com/VsonicV/es-at-scale
```

Previously audited commit:

```text
574a9d134da1ffce2a8bb812019899e5c96b588a
```

Important findings:

- current main trainer uses static-wave-like assignment;
- archive contains completion-driven dynamic dispatch using `ray.wait`;
- therefore greedy dynamic scheduling is a mandatory baseline, NOT project novelty;
- current WorkerExtension resets a generator with the same seed per parameter, which can create correlated/same-prefix noise behavior;
- restore is arithmetic negative perturbation, not exact snapshot restore;
- useful pattern: FP32 update accumulation;
- timeout may be converted into reward 0, which HeteroES should NOT copy because infra failure should be distinguished from task reward;
- license is Academic Public License, so provenance matters.

## yunpengba7/understanding-es

Important findings:

- strong experiment/config/manifest discipline;
- reference full run expects homogeneous GPUs on one host;
- static seed sharding;
- stable tensor ID improvement;
- still relies on device-native torch Generator / randn;
- perturb + arithmetic negative restore;
- replicas reconstruct updates locally from seeds and rewards;
- periodic synchronization exists.

Therefore:

```text
replay
local reconstruction
periodic resynchronization
```

are NOT themselves novel.

HeteroES’s focus is heterogeneous physical replay consistency + explicit numerical contract + measurement.

## Agentic ESOpt

Project page:

```text
https://zz1358m.github.io/Project-Agentic-ESOpt/
```

Important findings:

- stable tensor ID + candidate seed + chunking;
- replay/resume history;
- chunked FP32 reconstruction/update ideas are useful;
- still relies on GPU-native torch RNG in relevant paths;
- replay history is not equivalent to HeteroES candidate/attempt/lease exactly-once correctness.

When relying on any of these findings during implementation or documentation, re-check actual source if details matter.

---

# 22. Documentation strategy

This project should be documented as a **software system with a numerical contract**, not just as an ML experiment.

Keep:

```text
HETEROES_LLM_MASTER.md
HETEROES_LLM_STATUS.md
```

Then gradually introduce engineering docs.

Do NOT create all documents at once.

Recommended eventual structure:

```text
docs/
├── requirements.md
├── architecture.md
├── numerical-contract.md
├── runtime-protocol.md
├── data-model.md
├── api-contract.md
├── testing.md
├── experiments.md
├── deployment.md
└── adr/
    ├── ADR-001-canonical-noise-engine.md
    └── ...
```

Also eventually:

```text
THIRD_PARTY.md
```

for provenance/licensing.

At the CURRENT phase, focus only on:

```text
docs/architecture.md
docs/numerical-contract.md
docs/adr/
```

Do not prematurely design full DB or REST APIs.

---

# 23. Architecture documentation style

`docs/architecture.md` should be concise and useful for implementation/defense.

Prefer these views:

## A. Problem / system context

Show:

```text
Researcher / user
        |
Product layer
        |
Coordinator
      /     \
5070Ti     1660S
```

## B. Major subsystems

Possible logical split:

```text
Product
Coordinator
Worker
Numerical Core
Ledger
Artifacts
```

## C. Numerical data flow

```text
Parent model
    ↓
ParameterSchema
    ↓
Candidate descriptor
    ↓
CanonicalNoiseEngine
    ↓
Perturb
    ↓
Inference
    ↓
Reward
    ↓
Restore
```

Coordinator update:

```text
valid candidate results
    ↓
reward standardization
    ↓
canonical noise reconstruction
    ↓
FP32 ES update accumulation
    ↓
new canonical model version
```

## D. State ownership

Document explicitly who owns:

```text
canonical model version
generation
candidate
attempt
lease
temporary perturbed worker state
worker replica
product users/workspaces
experiment queue
```

Coordinator/runtime owns ES correctness state.

Product layer must not own candidate/lease correctness.

## E. Deployment view

Current physical layout:

```text
5070Ti:
  coordinator + worker

1660S:
  worker

network:
  LAN / Tailscale / normal IP
```

---

# 24. Numerical contract document

`docs/numerical-contract.md` should eventually define:

```text
model identity
parameter schema
alias/tied-weight semantics
candidate seed namespace
NoiseEngine version
chunk identity
generation dtype
application dtype
sigma
perturbation
restore
ES update accumulation
reproducibility limits
```

An example invariant:

```text
Given the same:
- schema hash
- engine version
- candidate seed
- parameter index
- chunk index
- chunk size

the canonical noise bytes MUST be identical
on every supported worker.
```

This document is one of the most important technical artifacts in the project.

---

# 25. Architecture Decision Records

Use ADRs for major decisions.

Recommended first ADR:

```text
ADR-001 — CPU PCG64 as canonical cross-worker NoiseEngine
```

Structure:

```text
Status
Context
Decision
Alternatives considered
Consequences
Evidence
```

Context should capture the physical CUDA RNG mismatch.

Decision should describe the CPU PCG64 recipe.

Alternatives may include:

```text
native CUDA RNG
shipping full noise tensors
other counter-based / portable RNG choices
```

Consequences should include both advantages and costs.

Do not claim CPU PCG64 is theoretically the only possible solution.

It is the currently selected engineering contract based on evidence.

---

# 26. Software-engineering mindset

Whenever possible, map concepts to familiar software concepts.

Examples:

```text
ParameterSchema
≈ schema / contract for model parameter space

CandidateDescriptor
≈ immutable job request DTO

candidate_id
≈ logical job identity

attempt_id
≈ execution attempt identity

lease
≈ temporary distributed job ownership

canonical model version
≈ versioned authoritative state

NoiseEngine
≈ deterministic pure service/function

cross-machine regression
≈ contract/integration test across physical implementations
```

The project should be treated as:

```text
ML numerical core
+
distributed systems
+
backend/software engineering
+
experiment engineering
```

not as a pure ML notebook project.

---

# 27. Current recommended next action

Before writing more production code, first establish shared architectural understanding.

Recommended immediate task:

Create the first small version of:

```text
docs/architecture.md
```

containing only:

```text
1. Problem
2. System context
3. Major components
4. Numerical data flow
5. State ownership
6. Current deployment
7. Current implementation boundary
```

Keep it roughly 1–3 pages.

Do not design every future subsystem in detail.

After reviewing architecture together, proceed to:

```text
docs/numerical-contract.md
```

and then:

```text
docs/adr/ADR-001-canonical-noise-engine.md
```

Only after those concepts are understood should implementation of:

```text
src/heteroes/model/schema.py
src/heteroes/noise/contracts.py
src/heteroes/noise/engine.py
```

resume.

---

# 28. First thing to do in this Claude Code session

Do not immediately edit files.

First:

1. Inspect repository state.
2. Locate MASTER / STATUS and existing probe/notebook files.
3. Read the relevant sections.
4. Summarize back:
   - what currently exists;
   - what is verified;
   - what is not implemented;
   - what the next numerical gate is;
   - what documentation should be created first.
5. Show the proposed `docs/architecture.md` outline.
6. Wait for the user to understand/approve the architecture content before implementing substantial code.

Do not move directly into FastAPI, databases, schedulers, Docker, Kubernetes, or MLOps infrastructure.

The numerical identity layer comes first.