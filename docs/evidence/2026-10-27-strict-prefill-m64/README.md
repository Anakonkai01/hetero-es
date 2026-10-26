# Rejected M64 prefill tiles

Source `267ba0b5` and the frozen LDSM pilot from `../2026-10-27-strict-ldsm/harness/pilot-01.diff`.
RTX 5070 Ti, B22, M=888, random finite operands. All candidates match the M32/N64 projection bits;
PTX/SASS audits run on every build. Nine event observations, eight projections per graph replay.

| Source | K x N | M32/N64 | M64/N32 | M64/N64 |
| --- | --- | ---: | ---: | ---: |
| `267ba0b5` | 896 x 9728 | 494.1 us | 497.0 us | 529.9 us |
| `267ba0b5` | 4864 x 896 | 257.6 us | 256.4 us | 260.8 us |
| LDSM pilot | 896 x 9728 | 470.8 us | 479.3 us | 514.5 us |
| LDSM pilot | 4864 x 896 | 241.3 us | 245.3 us | 249.3 us |

M64/N32 keeps the output area per CTA while reducing weight conversions, but does not provide a useful
consistent gain. M64/N64 is slower and uses more local memory. Stop this direction; keep M32.
Raw observations, register/local/shared sizes and audit receipts are in `raw/tiles-*-01.json`.

## What this does NOT show

No selected runtime change, whole-model gain, independent CPU oracle for these large matrices,
SM86/native acceptance, managed qualification or achievement of the vLLM goal. The output comparison
uses the existing independently tested M32 kernel, not a new CPU implementation.
