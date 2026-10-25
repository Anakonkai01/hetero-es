# Call-local prepacked activation radix planes — 2026-10-25

Prototype from selected97f62431: quantize and pack once, reuse in every output tile. Live FP16 weights and all
integer sums/final rounding stay unchanged. No retained activation/content cache or quantized weight copy.

## What this does NOT show

Unselected prototype; correctness is distinct from trained speed and full cross-device/native/managed acceptance.
No claim of general model quality or completion of M0–M6. No push/merge/deploy or learning run.
