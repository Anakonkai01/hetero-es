# Runtime tools

Run from `runtime/` with `PYTHONPATH=src` and the qualified `heteroes-match` Python environment. These scripts are
retained because operational workflows and the report use them. Historical raw experiments in `../artifacts/`
are evidence and must not be rewritten.

| Purpose | Scripts |
| --- | --- |
| Worker/coordinator execution | `run_worker.py`, `run_coordinator.py`, `serve_weights.py` |
| Qualification and profiles | `profile_worker.py`, `study-manifest.py`, `check-local-study.py` |
| Recovery and record inspection | `export-recovery-point.py`, `chunk_text_record.py`, `compare_candidate_records.py`, `compare_generation_runs.py` |
| Host energy measurements | `rapl-publisher.py`, `heteroes-rapl.service` |
| Research campaigns | `cluster_runner.py`, `cross_gpu_sweep.py`, `failure_campaign.py`, `run_benchmark.py`, `reference_generations.py`, `run_one_candidate.py`, `o2_cross_gpu_check.py` |
| Offline analysis | `measure_sync.py`, `predict_admission.py`, `predict_cluster.py`, `summarize_benchmark.py` |

GPU commands require the owner's authorization, an explicit `--gpu` where supported and
`HETEROES_GPU_ACCEPTANCE=1`. Adding that environment variable does not turn a CPU check into permission to run a
campaign. The live lab is operated only through the repository's `scripts/local-lab.py` in its deployed clone.
