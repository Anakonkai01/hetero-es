# Tier 2d (predeclared, written before the run, 2026-10-22 ~08:00 +07)

**Why.** Tier 2c passed everything it could judge except (b2): adding 5070ti-nhut back one second after its LEAVE was
refused (finding 7). The fix (`ec5fdc0`) is deployed as `lf1-20261022-r11-candidate11` (lab and the three Linux agents).
Tier 2d repeats exactly tier 2c's (b1) and (b2), with no machine killed, on that build. Its result is the gate for tier 3.

**Spec** `tier2d.json` = tier 2c with seed namespace `gsm8k-demo-tier2d-20261022`. **Members:** 5070ti-nhan
(coordinator), 5070ti-nhut, 3060-thao, 1660s.

**Declared events** (`stage_tier2c.py <log> --no-kill --tier tier2d`): (b1) 5070ti-nhut OFF once generation index 2 opens,
LEAVE within 10 minutes; (b2) once index 3 opens, ON and added back, `worker_joined` and a committed 5070ti-nhut result
started after the request within 15 minutes. One add attempt, as in tier 2c.

**Pass criteria:** COMPLETED with 160 results, ≥ 1 audit, 0 mismatches, no quarantine; (b1) and (b2) in time; the lab
releases the run at its end with no hand action; parity (ledger replay + one regenerated generation) equal.
**Stop rule** unchanged.
