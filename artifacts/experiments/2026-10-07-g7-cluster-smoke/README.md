# G7 smoke: one run of the real cluster with the CUDA noise engine and the long workload (07/10/2026)

`run_benchmark.py --conditions B3x2 --candidates 4 --generations 2 --noise-engine cuda --workload cot_l3_q32`: a coordinator and three worker processes (two on the 5070 Ti, one on the 1660S) finished
2 generations in 80 s; every worker's `executor_ready` event says `torch_cuda_philox_chunked_f32_to_f16_v1` and `cot_l3_q32`. It only shows that the pieces start and agree on the recipe (the workers build
the recipe from the job and compare its hash at admission); the evidence of the engine is in `../2026-10-07-g7-cluster-benchmark/` and `../2026-10-07-g7-restore-tradeoff/`.
