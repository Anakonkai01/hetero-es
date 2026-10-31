# FINDINGS-B (application architecture) — reviewer B

Source: owner's colleague's notes in `~/projects/app_finding.md`, imported 2026-10-31.
Baseline: `58cf278c`. Q = maintainability; D = documentation. The original concerns are preserved below.

| ID | Area | Type | Priority | Finding / question | Proposed resolution | Status |
| --- | --- | --- | --- | --- | --- | --- |
| B-001 | `backend/` | Q | P2 | Lab Server is a modular monolith; flat Python modules are difficult to navigate. | Plan B: separate API, services, repositories, DB, core and application entrypoints, then deploy multiple services. | Open |
| B-002 | `backend/routes_*.py` | Q | P2 | Routes mix HTTP handling, business rules and SQL without a separate application-to-database layer. | Plan B2: thin routers calling services and repositories. | Open |
| B-003 | `backend/store.py` | Q | P2 | `Store` aggregates SQL and supports SQLite only. | Plan B2–B3: a thin facade and repositories over SQLite/PostgreSQL transactions. | Open |
| B-Q1 | Lab Server responsibilities | D | — | How many server roles does Lab Server currently perform? | Document the current process and target service boundaries in `docs/design/lab-server-architecture.md` (A5, B1). | Open |
| B-Q2 | Data and backups | D | — | Where are experiment results and component backups stored? | Document product metadata, per-run ledger/checkpoints, recovery objects, metadata backups, installers and evidence (A5). | Open |

The colleague's parenthetical text denotes examples, English explanations or personal comments. These notes do not claim
that the existing modular monolith is a correctness defect; the approved multi-service work is tracked as architecture.
