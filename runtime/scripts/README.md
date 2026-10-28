# Runtime tools

Run from `runtime/` with `PYTHONPATH=src` and the qualified `heteroes-match` Python environment. These scripts are
retained because operational workflows, tests or acceptance probes use them. The research-campaign, benchmark and
vLLM/SGLang probe scripts were removed on 2026-10-28 (see `docs/REVIEW-GUIDE.md`); historical raw experiments are on the
branch `evidence-archive`.

| Purpose | Scripts |
| --- | --- |
| Worker/coordinator execution | `run_worker.py`, `run_coordinator.py`, `serve_weights.py` |
| Qualification and profiles | `profile_worker.py`, `study-manifest.py`, `check-local-study.py` |
| Recovery and record inspection | `export-recovery-point.py`, `chunk_text_record.py`, `compare_candidate_records.py`, `compare_generation_runs.py` |
| Host energy measurements | `rapl-publisher.py`, `heteroes-rapl.service` |
| Single-candidate and generation records (Recipe v1) | `run_one_candidate.py`, `reference_generations.py`, `build_golden_identities.py` |
| Datasets, v3 references and checkpoints | `build_*_dataset.py`, `build_v3_reference.py`, `v3_evaluate_checkpoints.py`, `v3_gpu_acceptance.py`, `translate_recipes_v3.py` |
| Strict engine probes (used by `acceptance/probes`) | `probe_strict_backend.py`, `probe_integer_decoder.py`, `probe_reference_backend.py`, `compare_strict_receipts.py` |

GPU commands require the owner's authorization, an explicit `--gpu` where supported and
`HETEROES_GPU_ACCEPTANCE=1`. Adding that environment variable does not turn a CPU check into permission to run a
campaign. The live lab is operated only through the repository's `scripts/local-lab.py` in its deployed clone.
