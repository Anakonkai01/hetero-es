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
