# Unselected B22 radix-carry scheduling experiment

Control source: `9acf8bfa`, including selected SM120 paired reads. The scratch variant replaces the
balanced-digit carry `(q-low)/256` by the equivalent signed shift `(q+128)>>8`, expressed as PTX
`shr.s32`. It changes neither the digit bytes nor their declared reconstruction within the admitted
integer range. No production source uses this variant.

Fourteen captured operator shapes were checked against the control and an independent CPU slice, then
timed on 5070 Ti and 3060. Some shapes improved substantially; others did not. The SM86 2560-to-960
shape regressed about 9.2%. Full-model ABBA on 5070 Ti checked equal parent token streams and found:

| Model | Batch 8 ratio | Batch 32 ratio |
| --- | ---: | ---: |
| SmolLM2-360M | 1.0071 | 1.0127 |
| Qwen2.5-0.5B | 0.9981 | 1.0112 |
| TinyLlama-1.1B | 0.9798 | 1.0126 |

The small batch-32 gains and regressions do not justify selection in this continuation. The owner's
later instruction prioritizes approaching vLLM with alternative arithmetic permitted; that work is in
[`../2026-10-25-fast-engine/`](../2026-10-25-fast-engine/README.md). Harnesses and both-host raw operator
receipts are preserved here, including the negative results.

## What this does NOT show

No selected optimization, canonical-candidate acceptance, broad numerical proof, quality, qualification,
managed execution or general speedup. These are operator/parent-model experiments, not learning.
