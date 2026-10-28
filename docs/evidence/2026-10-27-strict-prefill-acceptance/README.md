# Acceptance of the preceding prefill/weight-exponent change, 2026-10-27

Implementation `7ca91112`, sealed by `f3747900`, is compared with `a7884392`. Two prefill pipeline stages
and a three-CTA occupancy bound replace the preceding prefill launch; request weight-row exponents are
computed in one batched launch. Arithmetic and generated tokens remain unchanged.

Local source tests: **1014 pass**, with **5/5 batched-weight mutants killed** on frozen scratch.
Trained parent/canonical pairs/exact restore match for Qwen, Smol and Tiny on 5070 Ti and 3060 WSL2.
Qwen EOS coverage also includes the deliberately slow uncached path. Native Windows source run:
**856 pass** (18 min 16 s), trained Qwen parity and EOS pass. Native receipt and source manifests are
retained in `raw/3060-native-02/` and its archive; source manifest SHA-256 is
`0ac74633d27f008af5c7ab32d8116560151d4b51dc99ab2793b264292bcdec61`.

5070 Ti Qwen short32 ABAB rises from approximately **8910 to 9159 token/s**. The prefill configuration also
improves the 3060 WSL2 measurements (approximately **2804 to 2860 token/s**), so it was not restricted to
SM120. Exact per-round medians, outputs and source fingerprints are retained in the `single-*` JSON files.

The first two standalone WSL suite launches failed before tests because the copied pure-Python pytest
dependencies were incomplete (first stale dependencies, then the missing `py.py` compatibility shim).
Those failure receipts are preserved. A queued original-only retry was canceled before starting. We do
**not** claim a standalone WSL full-suite pass for `f3747900`: the subsequent frozen `267ba0b5` full WSL
suite includes the preceding prefill tests and passes **1054**, documented in the
[bounded-head acceptance](../2026-10-27-strict-bounded-lm-head/README.md).

The initial check-all's format failure occurred while subsequent bounded-head source was being developed.
Later source checks and packaging are scoped in that separate acceptance directory; this directory does
not turn the failed initial check into ALL PASS. `lm-head-red/green` logs here record test-first development
of the successor and are not prefill performance receipts.

## What this does NOT show

Finite source/operator/trained parity checks do not qualify arbitrary workloads, managed execution,
native installers, learning quality or the 80% vLLM objective. Native trained Smol/Tiny were not run.
No lab state, device approval, deployed process or historical numerical recipe was changed.
