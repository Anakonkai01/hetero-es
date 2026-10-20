# STOP: real audit mismatch; release acceptance did not pass

Experiment `e07deeb168ae4baaba3ac770b89043a6`, candidate5, attempt-2 spec declared in README.md before submission.
The release-plan stop rule was applied; no product or numerical code was changed.

## Ledger facts

- Paused cleanly at **13 applied generations**, **104 committed candidates / 104 attempts**.
- Commits: 5070 Ti **47**, Quang WSL 3060 **27**, Thao Windows 3060 **30**.
- **4 completed audits: 3 matched, 1 mismatched; zero quarantined workers.**
- Mismatch: `e07deeb168ae4baaba3ac770b89043a6/g10/c5` (zero-based generation 10, candidate index 5).
- Generating worker: `desktop-906949218c43` (5070 Ti); auditing worker: `cli-894b5d440398` (Quang WSL 3060).
- Committed completion SHA256: `519e5172210e0b97dfc20a761c97caa4635056912d67f6120afb52213fca8471`.
- Audited completion SHA256: `42c3204f4d1ed47de9bf73e463ec5333b3587763134e478b65ae9d55ac589dab`.
- Coordinator audit timestamp: **2026-10-20 14:55:08.626002 UTC** (21:55 local).
- Parent weights: `dfbfa65cae82010b068371455d4462b6ad88572788c784d5b5a3f2a52b3a93d9`.
  Both selected worker traces have a verified one-update replay to this parent before their corresponding
  COMMITTED / AUDITED step. This does not determine whether decoding, input/context, audit routing or another path caused the mismatch.

The detached monitor recorded STOP_AUDIT and exited; the operator then requested a graceful pause.
Work already in flight completed before the final 13-generation boundary. The planned generation-20
hard stop / five-minute return was **not injected in attempt 2**. No independent GPU parity run was started after the stop.

## Receipts and preserved private state

- `audit-mismatch.json`: read-only SQLite projection with mismatched hashes, descriptors, generation context/update record,
  counts and paused state. No lease or device credentials.
- `committed-candidate.json`: descriptor, committed texts/hash and reward. The audit protocol records the auditor's hash;
  its full text was not retained in this receipt. Reproduce under a separate owner instruction to recover that text.
- `5070-worker-events.json`, `quang-worker-events.json`: environment, replay/restore and selected candidate/audit events.
  Cross-machine timestamps are not synchronized; use the coordinator ledger as the reference clock.
- `monitor.jsonl`, `operator-events.jsonl`: append-only background observations and the stop trigger.
- `final-lab-state.json`: all four devices contribution OFF, unallocated; experiment PAUSED; usage facts.
- `experiment-detail.png`: browser screenshot of the **PAUSED / 13 of 50 / 1 mismatch** view. `browser.json`: no page errors.
- A consistent SQLite backup plus recipe/plan/dataset/splits/state/events/usage is private at
  `.scratch/r11-long-run2/private-run-copy/` (never commit its SQLite files: ledgers contain leases).
- Original coordinator state: Thao WSL `~/.local/share/heteroes-c4-cpu/agent-state/runs/e07deeb168ae4baaba3ac770b89043a6`.
  Parent/child weights and recovery points: `artifacts/coordinators/<run id>` under the same CLI home;
  `artifacts` resolves to `/mnt/d/HeteroES-r11-long-data-20261020/artifacts`. No weights were pruned by the operator.

Reported usage for the accepted 104 candidates and four audits: **26,613 generated tokens**, **1,022 audited tokens**,
**169.18538465408528 reported GPU seconds**, zero coordinator GPU update seconds, coverage `partial: false`.
These are successful-execution measurements, not elapsed time, energy or independently attested billing.

## Final operational state

All four selected devices are OFF and unallocated. Thao coordinator CLI PID 11590 and Quang CLI PID 1432
were gracefully stopped and confirmed absent. The isolated Lab Server and Linux/Windows desktop apps remain
up and idle. The private candidate5 installer HTTP server remains as before. No live lab operation, installer
publication, device revocation, merge, push or tag occurred. Thao C: approximately **10 GiB**, D: **818 GiB**;
Quang C: approximately **20 GiB**. The original Thao Worker backup remains untouched.

## What this does NOT show

Not 50-generation correctness, not independent parity, not successful induced-failure recovery, not Windows
candidate5 quit/relaunch/uninstall acceptance, and not release readiness. No learning or speedup claim.
The root cause of the audit mismatch is **unknown**. A matched self-test and a matching parent hash do not
prove all subsequent generated texts match. Do not dismiss the mismatch as normal floating-point variation,
change the contract, raise tolerances, or bypass audits without the owner's next decision.
