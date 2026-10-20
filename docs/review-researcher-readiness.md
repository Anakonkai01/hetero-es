# Brief for a deep review: what is still missing for researchers and scientists? (opened 2026-10-20)

Written for a later Claude Opus session (or any strong reviewer) that starts cold. The owner wants an **independent
review**, not a continuation: read the primary sources yourself, read the project as it is, and report what stops a
researcher or scientist from using HeteroES for real experiments. Talk to the owner in Vietnamese, simply, and explain
terms from basics (the owner did not write the docs). Follow AGENTS.md (no push, no `Co-Authored-By`, no `pkill -f`,
GPU only with the owner's authorization). This brief changes nothing by itself.

## Why this review exists
While asking how training batches are chosen, the owner found that the batch **sampler is hard-wired**:
`runtime/src/heteroes/v3/documents.py:135` rejects any sampler except `sha256-python-random-sample-v1`;
`v3/data.py:129` `batch()` has one algorithm; `v3/run.py:169` fills the sampler name from a constant. Users set only
`batchSize` and `batchSeed`. The two reference implementations walk the data in shuffled epochs (see
`docs/es-literature-local-recipe.md`, last section); ours draws an independent seeded sample per generation (repeats
and gaps). Scorers, coefficient rules and alpha schedules are already extensible (declarative + pinned Python); the
sampler is not. **This is the first item of the list below, and a sign that other fixed choices may be hidden.**

## Primary sources to read yourself (do not trust this summary)
Local copies, never executed, not committed: `.scratch/literature/papers/*.pdf` and `.scratch/literature/repos/`
(es-at-scale, understanding-es; hashes in `docs/es-literature-local-recipe.md`). Re-download from arXiv if missing:
2509.24372v3 (ES at Scale), 2608.17310v2 (Agentic ESOpt, no code repo found), 2608.27351v2 (Understanding ES;
github.com/yunpengba7/understanding-es). Read the appendices, hyperparameter tables and the code, and search for
newer ES-for-LLM papers and implementations. Note what each does that HeteroES cannot express.

## Read the project as it is
`AGENTS.md`, `docs/HANDOFF.md`, `docs/handoff-es-formula-countdown.md`, `runtime/docs/v3-local-runs.md`,
`v3-product-runs.md`, `adr/ADR-008-*.md`, `numerical-contract.md`, the `runtime/src/heteroes/v3/` modules, the web UI
and the SDK/CLI. Run nothing heavy: GSM8K run 1 may be using the GPU (`.scratch/gsm8k/run1`).

## Questions to answer
1. **Fixed choices.** List every setting a researcher cannot change (or cannot change without editing frozen code),
   for example: batch sampler, decoding (greedy only? sampling, multiple samples per prompt), system prompt/template,
   reward shaping and normalization, optimizer (no Adam/momentum by design?), perturbation shape (full / LoRA /
   subset), sigma schedules, antithetic sampling, evaluation protocol (Pass@K, majority vote), stop rules.
2. **Experiment workflow.** Can a researcher define a task, run seeds and ablations, compare runs, resume a run,
   export results and checkpoints (HF format), and reproduce a run from the recipe alone? What is missing?
3. **Scale and models.** Largest model/context that works, multi-turn/agentic tasks (Agentic ESOpt), long outputs,
   non-text tasks; heterogeneous GPUs and the cross-device identity limit.
4. **Evidence and rigor.** Statistics (confidence intervals, many seeds), held-out discipline, forgetting checks,
   cost accounting (rollouts, tokens, FLOPs) so results are comparable with the papers.
5. **Usability for non-engineers.** Docs, errors, installation, what a first-time scientist cannot do alone.
6. **Risks.** Places where extensibility would break the numerical contract or replay identity, and how to extend
   safely (new versioned name + recorded in the recipe, old versions kept so old runs still replay).

## Deliverable
A dated report in a new `docs/evidence/YYYY-MM-DD-researcher-readiness/` folder with a README that ends with
**What this does NOT show**. Rank the gaps by (value to researchers) × (cost/risk), mark each as verified in code
or a hypothesis, cite `file:line` and paper sections, and propose an ordered r11/r12 backlog. Then tell the owner the
top five in Vietnamese. Do not change recipe formats without the owner's decision.

## Known backlog items already decided to record
- **Pluggable batch sampler** (r11): declarative samplers with name+version in the recipe (`random-sample@1` = today's,
  `epoch-shuffle@1`, weighted mix) plus a pinned-Python tier for self-hosted labs like scorers; deterministic in
  (dataset hash, generation, seed); keep `sha256-python-random-sample-v1` so run 1 and old runs replay.
- **Self-hosted multi-machine (to verify, owner question 2026-10-20):** the SDK/CLI runner (`v3/local.py`) allows Python
  scorers and Python coefficient rules, but its workers are threads on one machine; the shared lab (`lab.heteroes.site`)
  has approved remote devices but accepts declarative scorers only and does not run Recipe v3 yet
  (`runtime/docs/v3-product-runs.md`). So a researcher cannot combine a custom Python reward with several machines.
  The author read only `local.py`, ADR-008 decision 4 and `v3-product-runs.md`: check whether a self-hosted coordinator
  can already accept remote workers, and if not, how to allow it without breaking decision 4 (e.g. the researcher's own
  coordinator, workers that never execute researcher code and only apply recorded coefficients/rewards).
