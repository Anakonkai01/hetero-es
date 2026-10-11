# Project progress and 20 November assessment — 11 October 2026

This is an engineering assessment, not a new acceptance claim or a change to
owner-authorized scope. There are 40 calendar days until 20 November 2026.
Canonical freezes remain 8 November for core/runtime and 15 November for results.
Read [the current handoff](m3-session-handoff.md) for operational continuation.

## What has been delivered

| Area | Current evidence | Remaining boundary |
| --- | --- | --- |
| ES numerical/runtime core | Canonical noise/parameter identities, exact parent restoration, standardized one-point updates, deterministic records and verified checkpoint lineage; real heterogeneous-device comparisons | Inference is not universally bit-stable across GPU/batch shapes; near-tie differences need a bounded policy and disclosed limits |
| Distributed execution | Candidate/attempt/lease ledger, dynamic and static baselines, epoch fencing, retries and confirmed process ownership; actual LAN/WAN worker runs | Earlier deployments do not automatically accept every newly packaged app/version |
| Performance research | Existing repeated benchmarks, N=48/96 scaling and raw artifacts; compact decoder reduces a measured generation from 150.8 to 94.4 seconds on its frozen workload | Gains are workload-specific. Admission predictions have known errors; reprofile the chosen final decoder and retain negative results |
| State synchronization/recovery | Full state transfer, replay with identity/hash checks, actual repeated fault campaigns; 100 recorded updates reproduced the stored hashes on each tested GPU in the earlier replay probe | Replay can be slower than transfer. New local pause/resume passes CPU equivalence but needs actual-GPU acceptance |
| Lab product M1/M2 | Accounts/approval, workspaces/roles/visibility, experiments and queue, outbound agents, pairing/revocation, CPU control, local event buffering, checkpoint publication and local recovery | Real cloud provider acceptance deferred; owner review remains necessary |
| Worker and CPU Server M3 | Windows/Linux packages and isolated pinned runtimes; native Windows RTX 3060 candidate/replay/baseline trial; actual Linux portable GPU qualification; fresh Linux CPU Server bootstrap/tray/restart | Linux leased candidate/replay/outage lifecycle, clean-machine/native Windows current UI/Server and ordinary desktop walkthrough remain pending |
| Scheduling M4 | Atomic physical GPU UUID ownership, disjoint assignment logic, eligible FIFO and generation checkpoint pause/resume | Real simultaneous multi-GPU scheduling and GPU pause/resume pending |
| Web/app experience | Home/auth, navigation, themes/languages, generation/candidate/seed inspection; shared Overview/Detail, larger text, actual CPU/GPU/RAM/disk/network/process/sensor readings | Automated layout checks and Xvfb are evidence of behavior, not owner usability acceptance or Windows sensor parity |
| Power and energy | Actual local CPU package RAPL and selected-GPU readings; private persistent session/day/month/lifetime component energy with coverage and hardware deduplication | Whole-machine AC requires a real meter; CPU+GPU is only the observed component subtotal, with unmeasured devices explicitly unavailable |
| M5 model/data/Recipe v2 | Pinned literature review and frozen proposed numerical/evaluation contract | Implementation, split-safe import, schedules, selected checkpoint evaluation and independently reloaded export remain pending |
| M6 and delivery | Existing research fault evidence, packaging checks, claim/report drafts, backups and reproducible artifacts | End-to-end updated-product fault/rollback/fresh-machine acceptance, full claim audit, report refresh, ownership/provenance and rehearsed demo remain pending |

Current checks: Track A 2,060 passed/100 skipped plus 24 targeted monitoring/Agent
checks; Track B 99 backend, Worker 12 Node, Server 1 Node and fleet 2 tests;
Web lint and all three builds passed. UI evidence includes 52 live-page layouts,
48 dedicated monitor layouts and 26 desktop fixture/theme cases. These checks
are not a count-based estimate of completion or a substitute for GPU/owner gates.

## Research interpretation

The strongest defensible contribution is the heterogeneous ES execution system:
portable numerical contracts, valid-result ownership under faults, measured
scheduling/admission trade-offs and synchronization cost. Generic dynamic queues,
seed replay and ES itself are prior art, not inventions of this project.

The earlier single-workload decoder comparison shows a 1.60x generation speedup;
it is not evidence of universal cluster speedup. Earlier 5070 Ti + 3060 N=48/96
comparisons report approximately 1.32/1.33x cluster benefit on their fixed
configuration. Preserve source conditions and repeats when presenting them.
Admission made at least one wrong decision, and some optimizations did not help;
reporting these makes the systems evaluation more credible.

Learning experiments already exist, but they do not establish robust general
reasoning improvement: early gains were confounded by output-token truncation;
later in-family gains coincided with prompt/answer-style effects and worse
out-of-family accuracy, with insufficient replication. A working ES training run
is not a demonstrated fine-tuning improvement. Literature-inspired Recipe v2 is
currently a proposal, not a replicated paper result. The new learning evaluation
must separate task/format reward, freeze validation/test use and compare base and
independently reloaded selected exports across multiple seeds.

## Overall assessment

The project is beyond a prototype in runtime behavior and local lab operations,
with substantial actual hardware evidence. It remains a research/lab product
under acceptance rather than a broadly qualified release. The weakest parts now
are evidence closure for the latest product, learning/generalization claims and
human review/defense readiness, rather than adding more interface features.

The old 88–90% figures evaluated a narrower research scope before M1–M6 and this
UI expansion. They must not be reused as whole-project completion percentages.
Implementation, hardware acceptance and delivery readiness are separate axes;
there is no validated single percentage for the expanded project.

For a two-student IT engineering capstone, the scope and evidence are substantial.
A strong submission is feasible if it explains C1–C4 clearly, provides a clean
local install-to-result demonstration, audits a bounded experiment matrix and
honestly reports learning/negative results. More features alone do not increase
the credibility of the submission. Both students must understand and demonstrate
their components, numerical/control boundaries and AI-assisted provenance.

## Deadline judgement and recommended execution gates

**20 November is feasible for a bounded, well-evaluated local capstone.** It is
not a reliable promise of complete M1–M6, broad Windows/Linux hardware parity,
cloud acceptance, multiple models and replicated fine-tuning gains. Those require
separate gates and external hardware. The current deadline risk is moderate for
the bounded submission and high for the entire expanded wishlist. This is a
qualitative engineering judgement, not a measured probability or grading forecast.

| Dates | Recommended outcome / decision gate |
| --- | --- |
| 12–18 October | Owner UI/flow review; latest Linux Worker candidate/replay/baseline and OFF/Quit/restart/outage gates; real local GPU pause/resume; list the minimal deliverable and pending external-hardware gates |
| 19–25 October | Implement the smallest coherent M5 path: one pinned model, one task/data pipeline, frozen splits/Recipe v2, evaluate/export/reload; pilot before committing to the larger population/seed matrix |
| 26 October–1 November | Execute a bounded frozen experiment matrix with repeats and base/held-out evaluation; update admission profiles; opportunistic short remote acceptance, without depending on borrowed GPUs for daily progress |
| 2–8 November | Integrated product fault/recovery and restore checks, fresh-install walkthrough, material fixes; core/runtime feature freeze on 8 November |
| 9–15 November | Final repeats/figures, owner acceptance, trace every reported claim to raw artifacts, finalize reproducible demo; result freeze on 15 November |
| 16–19 November | Release-candidate smoke, report and ownership/provenance audit, slides, fallback video and role-swapped rehearsal; no architectural change |
| 20 November | Submit early and verify deliverables; retain the demonstrated environment |

These are recommendations to prioritize the authorized work, not automatic
permission to mark missing gates passed or silently cancel owner requirements.
Keep cloud deferred under the owner's current instruction. Prefer one evaluated
model/task over broad shallow model support; treat GRPO comparison and extra
hardware/provider breadth as optional unless the school rubric requires them.
If 25 October arrives without a reproducible M5 pilot, reduce experiment breadth
and retain a systems-focused report with explicit learning limitations. If
1 November lacks stable end-to-end packaged evidence, prioritize the proven
local path and document unaccepted platform/hardware gates.

The assessment assumes a capstone evaluated primarily as an IT engineering
system. The exact school rubric, required report format and presentation duration
have not been supplied; a mandatory algorithmic improvement or provider/platform
requirement would change this deadline judgement. Removing GPU budget caps helps
compute availability but does not remove hardware access, evidence or review work.
