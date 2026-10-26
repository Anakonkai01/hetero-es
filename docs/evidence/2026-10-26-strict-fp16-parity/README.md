# Vendor FP16 GEMM fails the finite heterogeneous token gate

Runtime base: selected B22 `b1ef257a`; receipt HEAD at entry: `01e13637`. The owner asked about the
separate 7,492/7,804 token/s FP16 projection control. This survey tests that own decoder with vendor
FP16 GEMM directly; it does not execute vLLM. No selected runtime source changed.

The same pinned Qwen model, first 32 recorded GSM8K chat prompts, parent and canonical seed 7001
plus/minus at sigma 0.001 run on 5070 Ti Linux and 3060 WSL2. Restored parent is also measured.
Each configuration uses batch 8/32, greedy generation, EOS stopping and at most 128 new tokens.
Both hosts use matching probe source, portable backend identity, model file/schema/parent hashes,
input token IDs and candidate weight hashes. Final restore is exact; inference leaves weights intact.
One live merged FP16 weight set is primary, with a CPU snapshot and no second full GPU model.

Two policies are measured. `default` records FP16 reduced-precision reduction allowed, FP16
accumulation disallowed and TF32 disallowed. `fp32_acc` also disables FP16 reduced-precision
reduction. These are matmul accumulation flags, not an FP32 model shadow. Captures are released
before policy changes. The process-local flags are restored on exit.

| Cross-GPU comparison, excluding restored duplicates | Rows | Different token rows | Reward flips |
| --- | ---: | ---: | ---: |
| Default, batch 8 | 96 | 14 | 0 |
| Default, batch 32 | 96 | 33 | 0 |
| FP32 accumulation policy, batch 8 | 96 | 14 | 0 |
| FP32 accumulation policy, batch 32 | 96 | 26 | 0 |

Each denominator is 32 questions times parent/plus/minus, not 96 independent questions. The batch
and policy rows repeat those inputs. At batch 32 only one of 96 answers finishes on either host,
and all observed scores are zero; this short-budget reward agreement supplies no useful evidence
of a small reward/learning effect. Token disagreement alone violates D2.

A concrete default/batch-32 counterexample is the unperturbed parent on `gsm8k-test-002`, zero-based
output position 4: token 106987 on 5070 Ti versus 26242 on 3060. Under the FP32 accumulation policy,
the same parent/question differs at position 7: token 21322 versus 99235. Full streams, weights,
inputs and identities are retained in the host JSON files.

Within each host, parent/restored output streams match. Batch 8 versus batch 32 differs in 197/256
rows on 5070 Ti and 206/256 on 3060 when aggregating both policies and all four weight states,
including restored duplicates. These are repeated finite comparisons, not independent rates.

The identity-gated comparer passes two CPU tests. Both deliberate mutations are killed: hiding token
changes when rewards match, and ignoring model-asset identity. No new GPU acceptance suite is claimed
from these CPU tests. Probe wall times include compilation/capture and are not new throughput claims.

Conclusion: this specific 7.8k vendor-projection path is now demonstrated to fail D2 in the measured
configuration; it is no longer merely missing a heterogeneous check. Do not select it under the
current strict constraints. This does not rule out all possible future GEMM-based deterministic designs.

Final harnesses and SHA256 manifest are retained. Reproduce with the isolated matching Python,
`PYTHONPATH=runtime/src:<folder>/harness`, `HETEROES_GPU_ACCEPTANCE=1` and probe `--gpu`; the helper
analyzer names the recorded evidence paths. The approved standalone 3060 run uses the existing selected
source and process-local WSL CUDA library path. No device approval/contribution state was changed.

## What this does NOT show

General reward or learning impact, a 512-token completed-answer benchmark, universal numerical
properties of every vendor GEMM, native Windows acceptance of this control, managed activation,
near-vLLM own-kernel performance or M0–M6 completion. No push, merge or deployment occurred.
