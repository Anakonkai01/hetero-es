# Guarded normal-domain nonlinear nodes, 2026-10-27

Unselected SM120 research against `0eb86cb9`. Keep every original FP32 multiply/add, rounding point,
Newton iteration and Horner coefficient. Inside a bounded domain where intermediates cannot be nonzero
subnormals or nonfinite, omit their redundant integer flush/classification. Outside it, call the original
implementation. No hardware FTZ, contraction, approximate reciprocal or vendor exp is introduced; the
original PTX/SASS audits pass unchanged.

V1 specializes reciprocal and rsqrt for the existing `[DOMAIN_LOW, DOMAIN_HIGH]` interval, approximately
`[1e-30,1e30]`. Seed accuracy and Newton envelopes keep intermediate magnitudes well inside normal FP32.
V2 additionally specializes exp on `[-80,80]`; `|x| <= 2^-26` yields exactly one in the original polynomial.
The range-reduction lattice and bounded polynomial keep the remaining specialized intermediates normal
or zero. This is distinct from the previously rejected reciprocal lookup table and unguarded hardware FTZ.

## Finite evidence

- `raw/tests-02.log`: **2 passing** tests: 2^20 random bit patterns plus domain/zero/subnormal/nonfinite
  edges, and composed SiLU/RMSNorm/prefill attention. Finite outputs are compared by bits; nonfinite
  classifications and both failure bits are compared. Arbitrary NaN payload identity is not asserted.
- `raw/exp-tests-01.log`: **1 passing** test, 2^20 random encodings plus clipping/tiny-guard boundaries
  and nonfinite cases, with the same output/flag comparisons.
- `raw/exhaust-02.json`: **all 1,671,934,059** positive FP32 encodings in the admitted reciprocal/rsqrt
  domain match original output bits and flags. **All 2,235,564,034** signed encodings from `-80` to `80`
  (including both zeros/subnormals) match the original exp. Instrumentation at every removed node check
  records **zero** subnormal or nonfinite hits. This is exhaustive on this GPU/compiler for these domains,
  not an exhaustive cross-architecture test or a replacement for a reviewed range proof.
- `raw/mutation-01.log`: control passes, **4/4 mutants killed**: one removed reciprocal iteration, one
  removed rsqrt iteration, invalid-domain bypass and an excessively wide exp shortcut.

`harness/exhaust.py` is the retained failed first diagnostic (local variable naming collision).
`exhaust_v2.py` fixes that and generates the successful receipt. The first primitive test also lacked
Torch context initialization; its failed receipt is retained separately from the passing retry.

## Performance screening and decision

The single-process five-sample full-request pilots preserve Qwen token hashes at batch 32:

| Variant | short32 token/s | chat128 token/s |
| --- | ---: | ---: |
| Reciprocal/rsqrt V1 | 9887.7 | 9894.7 |
| Exp + reciprocal/rsqrt V2 | 9908.0 | 9959.8 |

Nearby independent frozen-runtime controls in the [TMA experiment](../2026-10-27-strict-tma-pipeline/README.md)
average 9868.4 / 9885.6. These are **screening pilots, not matched ABAB gain estimates**; the changes are
too small to justify selection or broad acceptance work. Park both versions. The useful follow-on
hypothesis is to guard a much larger QK reduction tree, recorded separately. The selected runtime is unchanged.

## What this does NOT show

No near-80% result, selected runtime change, general omission of error checks, reviewed portable proof,
SM86/native Windows acceptance, trained candidate parity, quality/learning result, package qualification,
deployment or managed lifecycle claim is made. Full-model pilots are parent inference only. Out-of-domain
random tests do not exhaust every invalid encoding. Original failure paths remain in the prototype.
