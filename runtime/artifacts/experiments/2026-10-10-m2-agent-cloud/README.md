# M2 local agent/control/recovery campaign — 2026-10-10

Status: local implementation verified; **cloud gates pending**. No AWS/R2/DNS
resources were provisioned. The owner confirmed no cloud accounts yet.

`summary.json` records the actual GPU runs, per-worker result commits, checksums,
shutdown and conservative budget. `baseline-evidence.json` proves exact final
checkpoint equality with the same run identity on one GPU. `outage-evidence.json`
records the actual control API outage while compute advanced two generations.
Local compute/recovery results do not imply ES improves LLM quality on a held-out
task or establish public/untrusted-worker safety.

`local-restore-evidence.json` covers a fully verified local five-file point into
a fresh held directory. `metadata-restore-evidence.json` covers real local product
SQLite restore, preserved history/FIFO/reservations, session revocation and cold
API/cache access. Neither is a restore from R2. `m1-sample-export.json` records
the selected M1 checkpoint export prepared for cloud import, not an upload.

`browser-validation.json`, `cached-artifact-evidence.json`,
`migration-evidence.json` and `mutation-evidence.json` cover real browser/CPU
behavior, exact import preservation and caught scratch mutations.
`service-return-evidence.json` records the safe end state: M1 restored, isolated
M2 agents stopped/OFF, M2 queue held, no outstanding M2 reservations.

Secrets, raw logs, screenshots, live databases, model weights and process records
are private outside Git. Earlier evidence folders are unchanged. Canonical design
and actual status are in `HETEROES_LLM_MASTER.md`/`HETEROES_LLM_STATUS.md`; the
accepted roadmap and cloud setup guide are in sibling Track B `docs/`.
