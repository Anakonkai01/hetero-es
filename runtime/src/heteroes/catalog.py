"""
The names the product may offer, defined ONCE: the pinned checkpoint of Recipe v1, the built-in workloads and the decode engines.

Standard library only, because the backend imports it without NumPy or torch. Changing a value here changes recipe identities
(`heteroes.manifest`) and what shipped desktop workers accept; `tests/test_golden_identities.py` guards the recorded ones.
"""

# The checkpoint of every Recipe v1 experiment (model and tokenizer from the same snapshot).
PINNED_MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"
PINNED_REVISION = "7ae557604adf67be50417f59c2c2f167def9a775"

# The workloads a Recipe v1 can name (`heteroes.eval.workloads` holds what each name means).
WORKLOAD_NAMES = ("arith16", "cot_l3_q32", "cot_l3_q64", "cot_l1_q128")

# How the answers are generated: the library's generate() or the compacting greedy decoder (`heteroes.eval.compact_decode`).
DECODE_ENGINES = ("hf_generate", "hf_compact")

# A new opt-in Recipe v3 identity; never extend Recipe v1's frozen decoder vocabulary.
CPU_GUARD_DECODER = "hf_fp32_cpu_guard_v1"
# The strict B22 integer decoder over the live FP16 weights (ADR-013): same tokens on every supported NVIDIA GPU.
STRICT_B22_DECODER = "strict_b22_v1"
V3_DECODE_ENGINES = (*DECODE_ENGINES, CPU_GUARD_DECODER, STRICT_B22_DECODER)

# How the coordinator hands candidates to workers (ADR-009); the first is the default. Not part of any recipe identity:
# a policy only decides which worker evaluates which candidate.
SCHEDULER_POLICIES = ("greedy-tail", "greedy")
DEFAULT_SCHEDULER_POLICY = SCHEDULER_POLICIES[0]
SYNC_MODES = ("synchronous",)
