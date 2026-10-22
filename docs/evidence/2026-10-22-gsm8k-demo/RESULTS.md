# GSM8K demo: results

Written after the runs; the predeclaration is `README.md` (unchanged since commit `4a64f7f`). Receipts per tier are in
`tier1/`, `tier2/` and `tier3/` (timelines and events as the lab API returned them, parity receipts, staged-event logs).
Scripts: `verify_managed_run.py` (regeneration and ledger replay), `stage_events.py` (tier 2 events), `eval_base.py`
(base model on a split, scored like the lab's Tracker).

## Tier 1: smoke (experiment `6d034ac1cfaa48e6b9342ed067705cd8`), 21:52–21:59 +07

| Criterion | Result |
| --------- | ------ |
| COMPLETED, 16 committed results | **pass**: COMPLETED, 16/16 |
| 0 audit mismatches, no quarantine | **pass**: 2 audits, both matched across devices (a Quang candidate re-run on the 5070 Ti and the reverse) |
| Full regeneration on the 5070 Ti equal | **pass**: `tier1/parity.json` ALL EQUAL (16 candidates: texts, rewards, records; both child hashes, final `72874d9d…`) |
| `3060-thao` commits a result over the public route | **FAIL**: see the finding below |

Work: 5070ti-nhan 11 candidates (6.2 s each, 8 questions), quang-3060 4 (15.8 s), 1660s 1 (47.8 s), 3060-thao 0. Generations took
59 s and 37 s. Validation (64 rows): base 0.625, generation 2 0.641. The lab then evaluated the selected checkpoint once on
the 64 smoke test rows: 0.391, independent reload passed.

**Finding (product, design limit): the public compute route cannot carry a dataset run.** With Tailscale disconnected on
Windows, `3060-thao` got its START_WORKER command with the private coordinator URL and `publicComputeUrl`. The agent's
`study/prepare.py` refuses on purpose to fetch any study file over a public URL ("never route a large file through public
URLs"), and the dataset grant is the private origin. The worker therefore kept failing the dataset fetch (empty
`.pending-*` files on `F:` every 30–60 s), was restarted twice (`worker_restarted` launch 1 and 2) and never started.
Consequences: (1) a device without a private route cannot join any v3 run that has a dataset, even a 4 MB one; (2) the
finished run stayed DRAINING for about 4 minutes until that device confirmed its worker had stopped. The handoff's open
question ("does the replay-only route carry a v3 full-weight run end to end?") is answered: **no, not with a dataset.**

**Deviation, approved by the owner in chat (22:0x):** Tailscale was switched back on remotely on Thao's Windows
(`tailscale-ipn.exe` started in the user session, then `tailscale up`; node `desktop-qp0nta7-1`). Tiers 2 and 3 use the
private route for every member.

## Tier 2: system under stress (experiment `01f8c5df4ac84846a4beaf9599857935`), 22:05–22:41 +07

| Criterion | Result |
| --------- | ------ |
| 160 committed results, coordinator COMPLETED | **pass**: 160/160, runner COMPLETED 22:41:18, final `276a6a78…` |
| 0 audit mismatches, ≥ 1 audit, no quarantine | **pass**: 4 audits, all matched across different GPUs (Quang re-ran a candidate, the 1660S two, the 5070 Ti one) |
| (a) uneven work by speed | **shown**: 5070ti-nhan 90 (18.2 s per candidate of 32 questions), 3060-thao 44 (36.3 s), quang-3060 12 (40.7 s, until it vanished), 1660s 14 (90.9 s) |
| (b) quang-3060 OFF at index 2 | **recovered**: OFF requested 22:20:15; LEAVE effective at the next boundary (`worker_left` 22:26:38, 396 s) |
| (b) quang-3060 ON at index 3, must rejoin within 10 min | **FAIL**: no JOIN (see below) |
| (d) parity: ledger replay + one generation regenerated | **pass** (run 2026-10-21 ~23:40, after the session): `tier2/parity.json` ALL EQUAL, 5 child hashes rebuilt from the ledger (final `276a6a78…`), generation 3 fully regenerated on the 5070 Ti (texts, rewards, records equal) |
| Lab releases the finished run | **FAIL, still DRAINING** at the session's end (see below) |

Generations took 365, 357, 385, 420 and 426 s (four devices, then three). Mean batch reward 0.556, 0.484, 0.627, 0.642,
0.455. Validation (64 rows): base 0.625, final 0.594. The stop rule applies: **tier 2 does not open the overnight run.**

**What actually happened to quang-3060.** Its machine went offline at **22:18:44** (lab last-seen; Tailscale "offline";
SSH timed out) during generation index 1, *before* the scripted OFF at 22:20:15. The run kept going on three devices: its
unfinished work was taken by the others and nothing failed. The rejoin could not have happened for two reasons. (1) The
machine was gone. (2) By design (ADR-009, `backend/agent_scheduling.py:auto_join`), a worker that LEFT an experiment is
never auto-joined again: the owner must add it back explicitly (`POST /api/v1/experiments/{id}/workers {"action":"add"}`).
Contribution ON alone does not do it. The predeclared step expected the wrong mechanism.

**Finding (product, serious): an offline member blocks the release of a finished run indefinitely.** The coordinator
completed, and its membership lists quang-3060 as `left`. But its worker state for it is still `alive: true,
confirmed: false` (the device cannot confirm a stop while offline). `release_left_members` needs `left` in the worker
state or a confirmed stop. `_release_confirmed` needs every device seen within 30 s. Neither has a timeout. So the lab
keeps the run DRAINING, and the reservations of **all four** devices stay held. No other experiment can start until the
missing machine comes back. In tier 1 the same mechanism only cost about 4 minutes, because Thao's device was online.

**Finding (product): `/api/v1/events` is too slow to poll.** It rebuilds the events of every run each time. While tier 2
ran it answered HTTP 524 (the Cloudflare edge gave up after 100 s), whereas the per-run timeline answered in 0.5 s. The demo
tools now read the timeline and the coordinator's own `events.jsonl`.

**Harness mistakes (the AI's, not the system's), recorded so nothing is hidden:** the first tier 2 event script died on a
transient `Connection reset by peer` before it acted (`tier2/stage-events-attempt1.jsonl`); it was restarted with retried
reads before generation index 2 opened, so the declared timing was kept. One script was first named `operator.py`, which
shadows the standard library.

## Tier 2b: explicit rejoin, five devices (experiment `90147d801ca8463d92143d21f95d63f4`), 23:20–23:46 +07

Run after the night session, once quang-3060 came back (23:00) and the lab released tier 2 by itself. Fifth member
`5070ti-nhut` added by the amendment committed before the run (`59d6189`).

| Criterion | Result |
| --------- | ------ |
| COMPLETED, 160 committed results | **pass** (numerically): runner COMPLETED 23:46:04, 160/160, final `3e02c708…` |
| 0 audit mismatches, ≥ 1 audit, no quarantine | **pass**: 5 audits, all matched across GPUs (1660S ×2, 3060-thao ×2, 5070ti-nhut ×1) |
| (b1) quang-3060 OFF at index 2, LEAVE within 10 min | **not a valid pass**: the harness said "recovered" (291 s), but the machine had already died at **23:29:19**, before the OFF (23:31:03). The LEAVE (23:35:05, actor `system`) came from the dead device. |
| (b2) ON + add back at index 3, JOIN + result within 15 min | **FAIL**: add refused `409 Waiting for confirmed GPU release` (the dead device's reservation, finding 1) |
| Parity | **pass**: `tier2b/parity.json` ALL EQUAL, 5 child hashes rebuilt from the ledger (final `3e02c708…`), generation 3 fully regenerated on the 5070 Ti |
| Lab releases the finished run | **FAIL, DRAINING** (below) |

Work: 5070ti-nhut 61, 5070ti-nhan 60, 3060-thao 26, quang-3060 8, 1660s 5. Validation (64 rows): base 0.625, final 0.625.
The 1660S also went down during the run (last seen ~23:39; it rebooted by itself ~23:42, its agent was restarted at 00:14).

**Finding 6 (serious, coordinator side):** the coordinator's supervisor waits for every member worker to confirm its stop
before it reports COMPLETED (`run_supervisor.poll_workers`, by design: an uncertain shutdown blocks the release). A dead
machine never answers, so the finished run stays DRAINING on the coordinator itself, not only on the lab (finding 1).
The 1660S cleared itself once its agent ran again; quang-3060 is still down. Fix on the branch (`e8f26a2`): a worker
unreachable for 10 minutes counts as stopped when the run drains. It changes a deliberate safety rule; owner review.

**Stop rule:** tier 2b failed (b2). The owner, informed, ordered tier 3 anyway and approved a hand release of the lab
database for the dead machines (`PREDECLARATION-tier2b.md`, owner decision). **Tier 3 has not started**: the coordinator
is still DRAINING because of quang-3060 (a separate hand edit of the coordinator's `state.json` was proposed to the owner,
not approved yet), so the lab release preconditions are never met (`then-tier3.jsonl` gave up after 60 minutes).

## Tier 2c: fixes under stress (experiment `43c37454015c4bb3ad1257ea3894a1e7`), 07:12–07:46 +07, lab and Linux agents on candidate10

Predeclared in `PREDECLARATION-tier2c.md` (commit `a1ff45a`, before the run). Members 5070ti-nhan (coordinator),
5070ti-nhut, 3060-thao, 1660s. Events in `.scratch/gsm8k-demo/tier2c-stage-events.jsonl`.

| Criterion | Result |
| --------- | ------ |
| 1. COMPLETED, 160 results, ≥ 1 audit, 0 mismatches, no quarantine | **pass**: 160/160 (5070ti-nhan 89, 3060-thao 41, 5070ti-nhut 28, 1660s 2), 7 audits all matched |
| (b1) 5070ti-nhut OFF at index 2, LEAVE within 10 min | **pass**: OFF 07:20:18, LEAVE applied at the boundary, seen after 439 s |
| (b2) ON + add back at index 3, JOIN + result within 15 min | **FAIL**: the add, one second after the LEAVE applied, was refused `409 Waiting for confirmed GPU release`; the script makes one attempt |
| 3. (c) 1660s killed at index 1 (07:16:22): `worker_lost`, lab release ≤ 11 min after the later of run end and kill + 10 min | **pass**: `worker_lost` 1660s at 07:44:07 (unreachable since 07:16:49); assignment released with the run's end, 0 reservations, no hand action |
| 4. 1660s back by its timer (07:56:22): ON by itself, idle, no worker of this run | **pass**: service started 07:56:24 (new boot), the lab turned it ON from Keep ON after restart (no owner action), `processes: []` |
| 5. Parity | **pass**: `tier2c/parity.json` ALL EQUAL (5 child hashes from the ledger, generation 3 regenerated on the 5070 Ti) |

**Finding 7 (product, fixed in `ec5fdc0`):** an owner who turns a worker OFF and adds it back right after the LEAVE is
refused, because the device is still reserved by this same run until its stop is confirmed. The lab now accepts that JOIN
(the reservation is this run's own; never another run's or the coordinator's) and the agent never starts the new launch
beside the old one. **Finding 8 (fixed in `ec5fdc0`):** after the lab released the left worker it refused the
coordinator's stop for it (403); the supervisor retried and logged `worker_left` every tick, and counted the worker
`lost` at the end. The lab now answers "stopped" for a worker it released, and `worker_left` is logged once.

**Stop rule:** (b2) failed, so by the predeclared rule tier 3 does not start on this result. Tier 2d repeats (b1)+(b2)
on the fixed build (`PREDECLARATION-tier2d.md`).

## Tier 2d: rejoin on the fixed build (experiment `366cb11c0af240a0a502baf9b6608bea`), 08:14–08:50 +07, candidate12

Predeclared in `PREDECLARATION-tier2d.md` (commit `8758c6a`, before the run). Events in `tier2d/stage-events.jsonl`.

| Criterion | Result |
| --------- | ------ |
| COMPLETED, 160 results, ≥ 1 audit, 0 mismatches, no quarantine | **pass**: 160/160 (5070ti-nhan 80, 3060-thao 39, 5070ti-nhut 27, 1660s 14), 13 audits all matched |
| (b1) 5070ti-nhut OFF at index 2, LEAVE within 10 min | **pass**: OFF 08:26:30, seen after 466 s; `worker_left` logged once (finding 8 fixed) |
| (b2) ON + add at index 3, JOIN + result within 15 min | **FAIL**: the add, 0.2 s after the ON, refused `409` |
| Release at the end, no hand action | **pass**: released, 0 reservations |
| Parity | **pass**: `tier2d/parity.json` ALL EQUAL (5 child hashes from the ledger, generation 3 regenerated) |

**Finding 7, corrected.** The 409 of tiers 2c and 2d was "Waiting for owner to turn contribution ON": the lab counts a
device ON only once its agent applied the ON at its next poll (up to about 10 s), and the script adds the worker 0.2 s
after the ON. The first fix (`ec5fdc0`, a re-add while the same run still holds the device) is a real case but was not
this refusal: the diagnosis in the tier 2c section was wrong. Fixed in `b5e1bc7`: a JOIN into a running
run needs the owner's ON only; the agent defers the worker's start until it has applied the ON. Not deployed.

**Stop rule:** (b2) failed again, so tier 3 does not start on this result. The owner had already decided that tier 3 is
for the next session (2026-10-22 ~08:40: "Nếu đạt tier 3 để phiên sau, phiên này dài rồi"). Next session: deploy the fix
and repeat (b2) before tier 3.

## Tier 2e: (b2) on the lab with the fix (experiment `c48ea62d743941b38ed497570f6b753b`), 09:14–09:46 +07

Predeclared in `PREDECLARATION-tier2e.md` (commit `cd4ab94`, before the run). Lab `a198cb0` = candidate12 + `b5e1bc7`
(deployed 09:12, `docs/evidence/2026-10-22-tier3/`); agents and web candidate12. Events in `tier2e/stage-events.jsonl`.

| Criterion | Result |
| --------- | ------ |
| COMPLETED, 160 results, ≥ 1 audit, 0 mismatches, no quarantine | **pass**: 160/160 (5070ti-nhan 75, 5070ti-nhut 39, 3060-thao 35, 1660s 11), 8 audits all matched, 0 quarantined |
| (b1) 5070ti-nhut OFF at index 2, LEAVE within 10 min | **pass**: OFF 09:23:58, LEAVE in the ledger at generation 3, seen after 439 s |
| (b2) ON + add at index 3, JOIN + result within 15 min | **pass in substance, the script's mark check failed** (below) |
| Release at the end, no hand action | **pass**: 0 reservations after COMPLETED |
| Parity | **pass**: `tier2e/parity.json` ALL EQUAL (5 child hashes from the ledger, generation 4, the one with the re-added worker, regenerated) |

**(b2).** ON 09:31:18, add 0.2 s later **accepted** (`JOIN`, `appliesAtNextGeneration`; tiers 2c/2d got 409 here). The
ledger records the JOIN at generation 4 (09:38:19, the next boundary); the coordinator logged `worker_restarted` (launch 1)
and 5070ti-nhut's first result after the request started 09:39:10 and committed 09:39:31 (492 s after the add); it
committed 11 results in generation 4. `stage_tier2c.py` waited for a `worker_joined` mark and logged `failed` after
900 s: the coordinator logs `worker_joined` only for a worker that was never a member of the run
(`run_supervisor._follow_membership`); a former member added back is started by `_restart_members`, which logs
`worker_restarted`. **Finding 9:** the declared mark was the wrong name for a re-add (the same check would never have
passed in tiers 2b-2d either); the event it stood for (the run takes the worker back and gets a result from it within
15 minutes) happened. Product follow-up (not during tier 3): log `worker_joined` (or show `worker_restarted` on the
timeline) for a re-added member.

**Gate decision (AI, owner's auto-run GO 2026-10-22 ~09:10).** Judged a pass: the refusal that failed (b2) twice is gone,
and the only miss is the name of a log mark, checked against the ledger and the coordinator's lifecycle log. Tier 3
starts on this result once parity is equal.
