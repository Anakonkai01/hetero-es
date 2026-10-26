# Strict prefill query/head tiles — native Windows follow-up, 2026-10-26

Follow-up to the sealed [prefill attention checkpoint](../2026-10-26-strict-prefill-attention/README.md), which left
native Windows acceptance pending. Runtime `2eb4da0d`, test-route fix `6cc69d26`, base `48547ba3`. The native job
was started by Codex before its handoff and finished on its own at 22:30 +07; Claude only collected the files.
The sealed checkpoint was not modified.

## What was run (3060, native Windows 11, Python 3.13.9, torch 2.13.0+cu132, CUDA 13.2)

From `raw/codex-prefill-native-run-01.json` (`status=ok`):

- Source archive SHA256 `bfaf5e6c…eb2`, 489 files; manifest equal before and unchanged after the run.
- Native pytest: **844 passed**, exit 0, 18 min 02 s (includes the new prefill tests and the earlier
  fused-finish/decode/32-column changes whose native gate was open since the Claude fused-finish handoff).
- Trained Qwen parent, canonical seed7001 ±sigma and restore, plus captured 32-row real EOS: exit 0.
- ABAB timing, one process per version per round, five warm samples each.

## Result

`summary.json` was produced by the sealed comparer
(`../2026-10-26-strict-prefill-attention/summarize.py --native-dir raw`); its console output is `summary.log`.
`nativeAcceptancePending=false`, `nativeManifestVerified=true`. Qwen parent/plus/minus/restored and EOS (27 rows
ending early) are equal across 3060 native, 3060 WSL2, 5070 Ti Linux and the sealed B22 receipts; restore exact.

| Host | Case | Base `48547ba3` | Query tiles `2eb4da0d` | Gain |
| --- | --- | ---: | ---: | ---: |
| 3060 native | Qwen short32 | 2664.3 | 2732.8 | +2.57% |
| 3060 native | Qwen chat128 | 2631.5 | 2704.5 | +2.77% |

Token hashes are identical between base and new (`bc4a5504…`, `a9fad5ca…`).

## What this does NOT show

- The full uncaptured EOS oracle was **not** rerun on native source: the receipt records
  `uncapturedEosControl.measuredInThisRun=false` and reuses the sealed fused-finish oracle after identity checks.
- Only Qwen was measured natively; Smol/Tiny native throughput and parity were not run here.
- Two ABAB rounds with one process each is a small sample; the native gain is indicative, not a tight estimate.
- No managed lifecycle, installer, live lab or universal hardware qualification (`hardwareQualified=false`).
- The performance objective (near vLLM 13835 token/s for Qwen short32 on the 5070 Ti) is still not met.

`native-live-console-01.log` is the local controller console copied after it finished.
