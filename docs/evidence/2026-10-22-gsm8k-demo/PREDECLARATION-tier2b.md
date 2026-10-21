# Tier 2b (predeclared, written before the run, after tier 2's event (b) failed)

**Why.** In tier 2 the declared rejoin step "contribution ON once generation index 3 opens; quang-3060 must rejoin and
commit within 10 minutes" did not happen. That was not a fault but the documented design (ADR-009,
`backend/agent_scheduling.py:auto_join`): an experiment never auto-joins a worker that already LEFT it; the owner adds it
back explicitly (`POST /api/v1/experiments/{id}/workers {"action": "add"}`, the path candidate9 used). By the stop rule, tier 2
does not open the overnight run. Tier 2b repeats tier 2 with the product's real rejoin path. Its result, pass or fail, is
the gate for tier 3.

**Same as tier 2** (`tier2b.json`): recipe, data, members, 5 generations, N = 32, batch 32, new seed namespace
`gsm8k-demo-tier2b-20261022`.

**Declared events** (`stage_events.py <log> tier2b --add`): (b1) quang-3060 contribution OFF once generation index 2 opens;
it must LEAVE within 10 minutes. (b2) Once index 3 opens: contribution ON **and** add quang-3060 back to the experiment. A
JOIN applies at the next generation boundary, so the deadline is **15 minutes** for both a `worker_joined` mark and a
committed quang-3060 result started after the request.

**Pass criteria** (as tier 2): COMPLETED with 160 committed results, 0 audit mismatches, at least one audit, no quarantine,
(b1) and (b2) recovered within their deadlines, ledger replay of every child hash and a full regeneration of one generation
equal. **Stop rule** unchanged: any failure means no overnight run.

## Amendment (2026-10-21 ~23:45 +07, before tier 2b ran)

**Members.** The owner added a fifth device: Nhựt's RTX 5070 Ti, `5070ti-nhut` (`cli-aa99b4d4ca58`, Linux CLI, joined
`https://lab.heteroes.site`, self-test passed, approved by the AI as admin on the owner's instruction). Tiers 2b and 3 offer
five members: 5070ti-nhan (coordinator), 5070ti-nhut, 3060-thao, quang-3060, 1660s. Nothing else changes: same specs
(`tier2b.json`, `tier3.json`), same declared events on quang-3060, same pass criteria and stop rule.

**Tier 3 length.** The owner confirmed G = 300 as declared (about 23-25 h with five devices).

**Known risk, recorded before the run.** quang-3060's machine rebooted uncleanly at 22:18 (Windows Kernel-Power 41 with a
fatal WHEA boot record, no bugcheck; three unexpected shutdowns in 30 days). If it drops again during 2b's declared events,
2b fails by the stop rule; in tier 3 a lost member is recorded and the run goes on.
