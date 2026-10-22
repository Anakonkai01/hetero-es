# Tier 2c (predeclared, written before the run, 2026-10-22 ~07:20 +07)

**Why.** Tier 2b failed its rejoin step because a member machine died, and the lab then held every device (findings 1
and 6). Fix wave 1 (`docs/evidence/2026-10-22-fix-wave1/`, lab and Linux agents on `lf1-20261022-r11-candidate10` since
07:05) claims to fix both. The stuck tier 2b run was already released by the deployed code at 06:56:50 without any hand
edit. Tier 2c repeats tier 2b's declared events on a machine that stays up, **and** kills another member on purpose, so
both paths are tested in one run. Its result is the gate for tier 3 (stop rule unchanged).

**Spec** `tier2c.json` = tier 2b's recipe, data, 5 generations, N = 32, batch 32; new seed namespace
`gsm8k-demo-tier2c-20261022`. **Members:** 5070ti-nhan (coordinator), 5070ti-nhut, 3060-thao, 1660s (quang-3060 is down).
5070ti-nhan, 5070ti-nhut and 1660s run the candidate10 CLI as a service with Keep ON after restart; 3060-thao runs the
candidate9 Windows app.

**Declared events** (`stage_tier2c.py`):

- (c) **killed**: once generation index 1 opens, every process of the 1660s Worker service is killed with SIGKILL (agent
  and worker at once, like a power cut: no OFF, no LEAVE, nothing confirmed) and the service is held stopped; a timer on
  the 1660S itself starts it again 40 minutes later. (A network cut with `iptables` was the first idea; the Claude Code
  permission classifier refused it, so the machine "dies" this way instead.)
- (b1) once index 2 opens: 5070ti-nhut contribution OFF; it must LEAVE within 10 minutes.
- (b2) once index 3 opens: 5070ti-nhut ON and added back; `worker_joined` and a committed 5070ti-nhut result started after
  the request within 15 minutes.

**Pass criteria:**

1. COMPLETED with 160 committed results; 0 audit mismatches, at least one audit, no quarantine.
2. (b1) and (b2) within their deadlines.
3. (c): the coordinator logs `worker_lost` for 1660s, and the lab releases the run (no reservation left) **at most 11
   minutes after the later of the run's end and the kill + 10 minutes**, with no hand action.
4. (c) when its service is back: 1660s turns ON by itself (Keep ON after restart), has no worker of this run alive, idle.
5. Parity: ledger replay of every child hash and a full regeneration of one generation equal.

**Stop rule:** any failure means no overnight run, unless the owner decides otherwise (recorded).
