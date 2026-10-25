# Human-review work by reasoning effort

Owner instruction, 2026-10-25: the unattended continuation prioritizes the strict kernel,
performance, vLLM source/paper review and general model/GPU coverage. Straightforward audit product work remains
reserved for a lower-effort session. The approved [M0–M6 plan](PLAN-SUA-HUMAN-REVIEW.md) remains the source of scope;
the in-repo copy preserves the original external plan bytes.
No push, merge, deployment, live device change or learning run is included.

## Earlier audit core checkpoint (closed at `1eaaecc`)

1. M2 audit accounting: canonical candidate outcomes, durable drain closure, restart and late-result races.
   Preserve historical sampling and three-mismatch ledger behavior, and keep `audit_counts()` compatibility.
2. M2 safety: a shared run-level guard across generation API rotation, serialized update admission, persisted faults,
   and a strict first-mismatch primitive retaining both execution receipts. Strict activation stays behind M4's real
   backend/recipe identity and qualification gates; an internal fixture does not make the current recipe strict.
3. Adversarial tests, scratch mutations and CPU integration checks for these core changes. Record precise limits.

## Captured strict checkpoint (`e05c9ab5`)

The owner specifically rejected optimization tied to a single Qwen checkpoint. The shared graph now admits a
restricted Qwen2/Llama/Mistral operator set, with four fixture layouts tested on four GPUs. Row tiling, coalesced
bounded staging, cached canonical RoPE and packed causal execution retain the specified FP32 trees.
Dimension-selected subtrees and bounded captured decode now extend that foundation, with original-owner KV slots,
request/candidate clearing, live weights, checked publication and stream-safe release. Three trained checkpoints
are benchmarked; native Windows and managed qualification remain open.
[Contract](../runtime/docs/strict-decoder-v1.md), [source/paper review](STRICT-PERFORMANCE-VLLM.md),
[receipts and limits](evidence/2026-10-25-strict-overnight/README.md),
[next heavy handoff](handoff-codex-strict-overnight-2026-10-25.md).

The current large-batch throughput remains far below vLLM. Projection throughput, wider
operator/trained-model coverage and qualification remain high-effort work. Integer/component Tensor Core designs
need a separate numerical contract/oracle and measured accuracy/range/memory behavior; no such backend is implemented.
The earlier audit accounting and safety work is unchanged, and M1/M2/M0–M6 remain incomplete.

## Next lower-effort session: bounded product work

Recommended **medium** effort for the first connected slice; **low** for isolated copy/documentation follow-ups.
Read the new handoff before changing anything; these are follow-ups after the core contracts are committed.

| Task                                                             | Concrete completion gate                                                                                                                                                                                                                         |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Project detailed audit outcomes through supervisor/backend/types | Read canonical ledger outcomes and durable per-generation drain reasons; count candidates once; preserve `completed`/`mismatches` API compatibility. Never derive matches from missing events. Mark old or missing operational evidence unknown. |
| Audit UI and translations                                        | Explicit disabled, pending, matched, mismatched, timed-out and skipped labels. Zero selected is not evidence of successful checking. Cover zero rate, no auditor, timeout and historical partial data with fixture browser checks.               |
| CLI/help and examples for existing audit controls                | Preserve explicit zero, frozen coverage and historical identities. Document that mid-run coverage changes are unsupported.                                                                                                                       |
| Routine receipt indexing and package reruns                      | Link the exact commits/checks; preserve failures and platform limits. Rerun packages after code changes that affect runtime contents. No native Windows claim from Linux source packages.                                                        |

Do not turn a low/medium-effort session into an unplanned numerical or recovery redesign. Use the committed
contracts; if a new cross-component invariant is uncovered, record it for the next heavy slice.

## Heavy work still in the full plan

These are **not** reassigned to low effort just because they remain after this session:

- M2 D11: meaningful progress by compute/sync/delivery/scoring/audit/update/recovery stage; monotonic deadlines,
  restart semantics and finite operator/researcher hard caps. Heartbeats must not refresh progress deadlines.
- M2 D10: persisted once-per-worker/run recovery budget; canonical reload, self-test/restore/probation and boundary
  rejoin, reconciling local poison, ledger/audit quarantine and supervisor state without device approval changes.
- M3: bounded recovery streaming/backoff, safe verification caching, retention dependency graph and measured
  early/middle/late bookkeeping. Carry the new audit drain/stop sidecars and reconcile faults later than an immutable
  recovery snapshot; replacement recovery does not yet preserve this strict guard. Real full-disk acceptance remains deferred.
- M1: projection throughput beyond captured decode, further arithmetic research and broader operator/model
  coverage; trained-model cross-GPU/native Windows and all-phase performance evidence. Shared RoPE/row/packed foundations
  are implemented, but existing SGLang/vLLM results and tiny graph receipts do not replace the remaining gates.
- M4: real backend/recipe identity and qualification namespaces, managed physical-GPU ownership, lifecycle and
  native packaging. Connect strict mismatch activation only here, with a supported qualified identity.
- M0 broader measurements, M5 full system acceptance and M6 frozen quantized base plus ES LoRA remain open.

The scheduling split changes the order of work within the approved plan. It does not mark M2, any untouched
milestone, or the overall objective complete.
