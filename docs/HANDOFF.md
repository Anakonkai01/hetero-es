# HeteroES — canonical handoff

**Latest: candidate6 installed; native Windows guarded decoder passes; waiting for Quang online (2026-10-21).**
Read [handoff-2026-10-21-candidate6-devices.md](handoff-2026-10-21-candidate6-devices.md) first.
Separate owner-approved FP32 + CPU-reference decoder: source f5d311b, final 23/23 combined checks PASS.
Candidate6 packages prepared and packaged checks PASS. Installed self-tests pass on 5070 GPU,
Thao Windows GPU and Thao WSL CPU. Quang install completed, but SSH/Tailscale is now offline.
Nine native Windows evaluations match 5070 token/text/input/weight arrays exactly; existing Quang
nine-case proof also matches. One initial Windows self-test ACTION_FAILED remains unexplained and retained.
The fresh 50-generation run is predeclared, not started. All four isolated contributions OFF; CLI agents stopped.
No merge/push/public release/live change. Flag-day confirmations still required. Historical state below is superseded.

Session 4 adds CPU coordination, eval/compare/serve/worker, real native Windows standalone coordinator proof, a limited
vLLM probe, prompt/scorer/usage features and partial Linux download wiring. Final full checks, candidate3 packaging and
managed/installer acceptance remain. The isolated lab/workers are stopped; public lab is unchanged. The latest handoff
is self-contained and supersedes older operational state and original-Worker restoration instructions.

## Current checkpoint

The approved one-repository cleanup (phases 0–6) is complete on `refactor/cleanup` and local `main`, fast-forwarded after
the final checks. No push/tag, live deployment update, device change or installer publication occurred.
The live clone remains `79876cb`; its published installers remain **lf1-20261014-r10**. A local `main` update does not
deploy that clone. The old repositories remain in `~/projects/_old/`, and both Git histories/old commit ids are retained.

Read [../AGENTS.md](../AGENTS.md) for common rules, [../README.md](../README.md) for layout/checks and
[archive/refactor-plan-vi.md](archive/refactor-plan-vi.md) for the owner's approved plan. Historical session chains and
runtime bootstrap guidance are in `archive/`; they are not additional current instructions.

## Completed changes

- One repository; runtime under `runtime/`, product at the root. Legacy control/SSH gateway, fake dispatch and old backup
  bundle are removed. The agent's live supervision was extracted before deleting the gateway.
- Web mock mode, unused routes, provider-specific cloud code, dead UI pieces and one-off M1–M3 tools are removed. The
  packaged r10 runtime was scanned before retiring routes. CPU telemetry/study code now has one runtime source.
- Local recovery is named `recovery_storage.py` / `metadata_backup.py`; restore tools use the same terminology. Existing
  `cloud_*` tables and recovery wire/cookie names remain compatible with stored data and r10 devices. Health retains
  `agentMode: true` and `deviceConfiguration: true` for shipped desktop clients.
- Shared backend policies/settings/configuration and Electron workspace helpers replace duplication. APIRouters and
  separate agent protocol/scheduling/command/poll modules keep responsibilities smaller. CREATE TABLE definitions are
  centralized without introducing a schema/data migration. Dense UI views now have dedicated components/hooks.
- Ruff/Prettier cover active source; raw evidence, archives, generated files and fixtures are excluded. All 287 existing
  Python ASTs were equal across formatting, including frozen Recipe v1. Formatting commit: `a3cf14ec86099fd17681279f34f065185873bc49` (also in
  `.git-blame-ignore-revs`). 310 unused translation keys were removed; the i18n checker now rejects unused keys too.
- One current entry point and common agent rule file replace the session chain. Scientific MASTER/STATUS/contracts,
  claims audit and raw runtime evidence remain. Existing numerical follow-ups are [RUNTIME-TODO.md](RUNTIME-TODO.md).

## Verification and receipts

The [completion receipts](evidence/2026-10-19-phase6/README.md) include the full 22-step CPU check and Linux unpacked builds in an
isolated source copy, ASAR shared-module import probes, and read-only public/deployed lab checks. Backend: **283 passed**;
runtime: **2,110 passed, 100 skipped**. Product browser/Electron probes use disposable fixtures and recorded runs.

Earlier phase receipts:

| Work | Receipt |
| --- | --- |
| Baseline, history-preserving merge and deployed-clone cutover | [2026-10-19-one-repo](evidence/2026-10-19-one-repo/README.md) |
| Legacy control removal and safe agent supervision extraction | [2026-10-19-phase2-runtime-removal](evidence/2026-10-19-phase2-runtime-removal/README.md) |
| Mock/cloud/dead-code cleanup and r10 route scan | [2026-10-19-phase3](evidence/2026-10-19-phase3/README.md) |
| Shared sources, policies and desktop utilities | [2026-10-19-phase4](evidence/2026-10-19-phase4/README.md) |
| Router/agent/UI splits, translation audit and mutation gap closure | [2026-10-19-phase5-structure](evidence/2026-10-19-phase5-structure/README.md) |
| 287-file AST proof, formatting/lint and CPU checks | [2026-10-19-phase5-format](evidence/2026-10-19-phase5-format/README.md) |

Mutation controls pass; final receipts kill 8 phase-2, 3 phase-3, 4 phase-4 and 4 phase-5 mutants. Phase 5 initially exposed
an untested ON/OFF poll response; the new regression kills that mutant. Retired-only tests and replacement counts are
explained in each phase README. The check command now includes runtime tests and Python/UI format/lint checks.

## Live state and remaining scope

The last read-only database check shows `5070ti` APPROVED and `3060-thao` **REVOKED**. Its audit records revocation on
2026-10-14; older handoffs saying APPROVED are stale. Do not approve or enable it from historical notes. Lab operations:
[local-lab-operations.md](local-lab-operations.md). User setup: [quickstart-vi.md](quickstart-vi.md).

No new GPU job, native Windows acceptance, fresh multi-GPU run or deployment of cleanup code is claimed. Installer
polish/r11, the next demo rehearsal, and identity/epoch/export features still pending in the ADRs are separate work.
The two existing security/policy findings are listed in [SECURITY-NOTES.md](SECURITY-NOTES.md); neither was silently fixed.

## Extensibility work (started 2026-10-19)

The owner approved an extensibility audit and eight design decisions: reward is scored on the coordinator from submitted
texts; reward identity lives outside the recipe; the shared lab accepts only declarative rewards; full/subset/LoRA weight
spaces; Recipe v1+v2 merge into one new format with ONE identity break (v3, released with desktop r11) that also makes room
for antithetic signs and coefficient rules; numerics stay bit-identical and old runs must replay to their recorded hashes.
Step 0 (branch `feat/extensibility-step0`, receipt [2026-10-19-extensibility-step0](evidence/2026-10-19-extensibility-step0/README.md))
changes no identity: recorded recipe/record/workload hashes and coefficients are tests, product names live in
`runtime/src/heteroes/catalog.py`, and `heteroes.executor.evaluate_task` is the single task seam.

ADR-008 is ACCEPTED (Q-A texts in the ledger, Q-B quarantine after 3 audit mismatches, Q-C one switch with r11,
Q-D antithetic off by default). Done on the branch: pure `heteroes/v3/` (documents, scorers, antithetic merge), subset
schemas, LoRA (`model/lora.py`, PEFT 0.21.2 in `heteroes-match` only), ledger schema 6 (signs, texts, audits; schema 5
refused as history), record version 2, and protocol v3 (workers submit texts, the coordinator scores them; antithetic
pairs). Receipts: `evidence/2026-10-19-extensibility-*`, `-v3-ledger-record`, `-v3-protocol`. Still to do: the product
runner/agent/backend/web on v3, audit scheduling, SDK/CLI, the r11 desktop profile (PEFT, Windows v3 acceptance), GPU
acceptance with the owner's authorization, and removing the v1/v2 run paths at the switch.
Detailed state and plan of this workstream for the next agent: [handoff-v3-extensibility.md](handoff-v3-extensibility.md).


## Product v3 continuation (2026-10-19)

Steps 1–3 of the extensibility handoff are implemented on `feat/v3-product-integration`: managed runner/agent/worker,
validation and verified selected export, and backend/web v3 configuration. The branch is local and unmerged; the live lab
and desktop release remain unchanged. Continue with [handoff-v3-product-integration.md](handoff-v3-product-integration.md)
for commits, CPU receipts, concrete limits and the remaining audit/r11/flag-day/GPU work. The existing recovery-point
format also needs v3 state/selection coverage before the flag day. No GPU, Windows or learning acceptance is claimed.

## Audit, recovery, GPU and SDK continuation (2026-10-19)

Continue from [handoff-v3-audit-recovery.md](handoff-v3-audit-recovery.md), branch
`feat/v3-audit-recovery`. Audit scheduling, complete v3 recovery and SDK polish are
implemented; the last complete combined suite is e35811c (22/22, 2,273 runtime
passed/100 skipped, 302 backend passed). Six Qwen Linux/WSL GPU cells pass exact
comparison/replay. Native Windows full/subset match; independently initialized
LoRA differs in initial adapter identity and is not cross-OS acceptance. r11 has
only an unwired WIP verifier, actual-OS dependency reports and a concrete remaining
plan. The owner authorized both GPUs/SSH and selected the 3060's Windows for the
next installer checks. No push, merge, release, live approval or deployment occurred.
The session ended at the owner's usage-budget request; read the detailed handoff
before resuming or claiming r11 readiness.

## r11 candidate1 (2026-10-19, later the same day)

Continue from [handoff-r11-candidate.md](handoff-r11-candidate.md), same branch. Section 5 steps 1–6 of the previous
handoff are done: the cross-OS LoRA cause is identified and a native Windows worker passes on a transferred adapter; the
desktop-v3 reference and profile are shipped in `desktop/worker/resources/`; the backend admits native Windows as a
reference-bound v3 worker only; unsigned candidate1 installers exist in `.scratch/` only. Not done: Windows installer
run (C: lacks space), owner install/uninstall acceptance, the stale Lab Server packaged check, and the flag day.

## Opened ES formula, Countdown/GSM8K, Worker data folder (2026-10-19/20)

Continue from [handoff-es-formula-countdown.md](handoff-es-formula-countdown.md), same branch: coefficient rules,
alpha schedules and momentum records; Countdown and GSM8K data; evaluation chunk; a Worker data folder on another drive;
checkpoint evaluation by replay; Countdown pilot 1 learned the format only, pilot 2 (300 generations) was running.

## System finish (2026-10-20, current)

The owner reframed the work: HeteroES claims a system, not that ES learns (see `AGENTS.md`, "Project claim"). GSM8K
run 2, the run 1 test/CommonsenseQA scoring and any parity run are **parked**. The owner-approved plan finishes the
system: the researcher's journey on an isolated r11 lab with the 5070 Ti and the native Windows 3060, Python rewards open
on the web lab, request-to-join, large datasets, any machine as coordinator plus a per-lab default coordinator,
`hf_compact` for v3, a vLLM probe, a pluggable sampler, `heteroes eval/compare/serve/worker`, prompt format, a boxed scorer
and cost accounting, then r11 candidate3. Continue from [handoff-system-finish.md](handoff-system-finish.md).

## Codex continuation paused by owner (2026-10-20)

Current continuation: [handoff-system-finish-next.md](handoff-system-finish-next.md) (session 2, 2026-10-20; the earlier Codex pause note is [handoff-system-finish-codex.md](handoff-system-finish-codex.md)). New-model qualification is implemented; the isolated two-machine comparison and the final CPU checks have since completed (see the next handoff). Windows original Worker restoration remains required after acceptance.
