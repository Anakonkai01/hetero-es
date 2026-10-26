# Smaller prefill tiles with higher occupancy: rejected

Frozen `0eb86cb9` B22 source, ldmatrix enabled, M=888. All variants compare complete FP32 output bits and
flags against the existing projection before timing; builds include PTX/SASS audits and resource counts.
Smaller M/N tiles increase resident CTAs but repeat more weight conversion and operand traffic.

| K × N | M32/N64, 3 CTAs | M32/N32, 4 CTAs | M16/N64, 4 CTAs | M16/N32, 6 CTAs |
| --- | ---: | ---: | ---: | ---: |
| 896 × 9728 | 473.1 µs | 507.7 µs | 549.1 µs | 620.8 µs |
| 4864 × 896 | 244.3 µs | 255.8 µs | 277.9 µs | 294.5 µs |
| 896 × 1152 | 66.2 µs | 63.4 µs | 68.8 µs | 73.0 µs |
| 896 × 896 | 51.3 µs | 51.3 µs | 55.1 µs | 58.2 µs |

The dominant MLP shapes regress. The isolated QKV improvement is too small to justify selecting this
strategy for the primary whole-generation goal. Keep the existing prefill tile. This extends the preceding
M64 pilot with previously unmeasured smaller M32/N32 and M16 configurations; it does not rerun or overwrite
the earlier evidence.

## What this does NOT show

These warm operator controls do not establish a full-decoder gain, a universal occupancy rule, a numerical
ceiling, other-platform qualification or managed/package acceptance. No runtime source was changed.
