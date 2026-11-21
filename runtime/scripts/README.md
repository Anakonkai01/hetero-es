# Runtime scripts

Run these commands from `runtime/` with `PYTHONPATH=src` and the qualified `heteroes-match` Python environment.
For a Recipe v3 run, start with the [CLI and SDK guide](../docs/v3-local-runs.md). The scripts below are used directly
by operators, tests and acceptance probes.

| Purpose | Scripts |
| --- | --- |
| Worker and coordinator processes | `run_worker.py`, `run_coordinator.py`, `serve_weights.py` |
| Qualification and profiles | `profile_worker.py`, `study-manifest.py`, `check-local-study.py` |
| Recovery and record inspection | `export-recovery-point.py`, `chunk_text_record.py`, `compare_candidate_records.py`, `compare_generation_runs.py` |
| Host energy measurements | `rapl-publisher.py`, `heteroes-rapl.service` |
| Single-candidate and generation records (Recipe v1) | `run_one_candidate.py`, `reference_generations.py`, `build_golden_identities.py` |
| Datasets, v3 references and checkpoints | `build_*_dataset.py`, `build_v3_reference.py`, `v3_evaluate_checkpoints.py`, `v3_gpu_acceptance.py`, `translate_recipes_v3.py` |
| Strict engine probes | `probe_strict_backend.py`, `probe_integer_decoder.py`, `probe_reference_backend.py`, `compare_strict_receipts.py` |

Use [the acceptance runner](../../docs/acceptance/README.md) to collect source-specific receipts. Use the deployed
clone's [lab operator commands](../../docs/guides/local-lab-operations.md) for the workstation service. GPU commands
require owner authorization and the opt-ins in [AGENTS.md](../../AGENTS.md). Archived benchmark and campaign scripts can
be found through the [review guide](../../docs/REVIEW-GUIDE.md#5-refactor-2026-10-28-đã-làm-gì-và-tìm-lại-ở-đâu)
and [evidence index](../../docs/EVIDENCE-INDEX.md).
