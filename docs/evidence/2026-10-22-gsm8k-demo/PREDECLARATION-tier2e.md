# Tier 2e (predeclared, written before the run, 2026-10-22 ~09:20 +07)

**Why.** Tier 2d failed only (b2): the add sent 0.2 s after the owner's ON was refused 409 "Waiting for owner to turn
contribution ON", because the lab counted the device ON only after its agent's next poll (finding 7, corrected). The fix
`b5e1bc7` (a JOIN needs the owner's ON only; the agent starts the worker once it has applied that ON) is deployed on the
lab alone as `a198cb0` = candidate12 + that commit (branch `deploy/candidate13`, `docs/evidence/2026-10-22-tier3/`), since
09:12. Agents and web stay candidate12. Tier 2e repeats tier 2d unchanged on it. Its result is the gate for tier 3.

**Spec** `tier2e.json` = tier 2d with seed namespace `gsm8k-demo-tier2e-20261022`. **Members:** 5070ti-nhan
(coordinator), 5070ti-nhut, 3060-thao, 1660s.

**Declared events** (`stage_tier2c.py <log> --no-kill --tier tier2e`): (b1) 5070ti-nhut OFF once generation index 2 opens,
LEAVE within 10 minutes; (b2) once index 3 opens, ON and added back at once, `worker_joined` and a committed 5070ti-nhut
result started after the request within 15 minutes. One add attempt.

**Pass criteria:** COMPLETED with 160 results, ≥ 1 audit, 0 mismatches, no quarantine; (b1) and (b2) in time; the lab
releases the run at its end with no hand action; parity (ledger replay + one regenerated generation) equal.
**Stop rule** unchanged: a failure stops here, tier 3 is not started.
