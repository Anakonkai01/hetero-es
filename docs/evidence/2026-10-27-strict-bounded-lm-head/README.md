# Exact bounded B22 lm_head, 2026-10-27

Frozen implementation: `267ba0b5d3b122bd10177e337ee0e83f686922f9`, against `f3747900`.
The proof and eligibility/fallback rules are in [bounded-lm-head.md](../../../runtime/docs/bounded-lm-head.md).
One compressed byte per live head weight gives outward integer intervals; only surviving 32-vocabulary
tiles are recomputed with the original nine signed-byte MMAs. Original rounding, lowest-index ties and
nonwinning overflow flags are retained. Initial prefill logits remain exact/full. Request-derived buffers
are refreshed and cleared, including failure paths. No second full inference model is retained.

## Measured result

Qwen batch 32, prefix caching off, identical generated tokens. Values are the mean of two independent
round medians in the ABAB controls, in token/s; these are complete generation timings.

| Host | short32 before | after | gain | chat128 before | after | gain |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 5070 Ti Linux | 9159.4 | 9392.8 | 2.55% | 9246.1 | 9557.5 | 3.37% |
| 3060 WSL2 | 2869.7 | 2968.9 | 3.45% | 2762.5 | 2878.0 | 4.18% |
| 3060 native Windows | 2854.4 | 2917.0 | 2.19% | 2767.9 | 2875.1 | 3.87% |

5070 Ti short32 is **67.9%** of the existing matched vLLM control (13834.6 token/s); the goal remains open.
[Machine-readable verification](raw/summary-01.json) was produced by [verify.py](harness/verify.py).

## Verification and provenance

- Frozen full suites: 5070 Ti **1054 pass** (979.57 s), 3060 WSL2 **1054 pass** (907.16 s), native Windows
  **896 pass** (1163.09 s, console inside the retained receipt archive). Native suite selection differs
  from Linux; do not sum these into a universal test count.
- Trained Qwen parent/canonical perturbation pairs/exact restore and EOS agree across all three hosts,
  and with the preceding sealed B22 evidence. Smol/Tiny trained cases agree on Linux/WSL2; their trained
  native cases were not run. No update or learning run was performed.
- **40 new tests** cover bounds, exact RNE overflow boundary and finite neighbor, ties/zeros/subnormals,
  max width, nonwinning negative overflow, conservative false-positive bounds, eligibility/fallback,
  request refresh/clearing and memory admission. **10/10 mutants killed** on frozen scratch; controls
  pass in [mutation-01.log](raw/mutation-01.log). The earlier slow sparse SIMT implementation is retained
  under `rejected/`; it was replaced with exact tensor MMA and coalesced candidate scanning.
- PTX/SASS audits pass for SM80/86/89/90/120. Only SM86 and SM120 have hardware evidence. SM75 is outside
  this integer runtime's supported targets. Two versus three bounded-score pipeline stages were measured;
  three remains selected, with no extrapolated end-to-end gain.
- `checks-01` completed all checks during development. The frozen-source `checks-02` completed all parts
  except Prettier, whose Git file enumeration exceeded Node's 1 MiB buffer. Commit `e496cc18` raises that
  buffer; [prettier-retry-03.log](raw/prettier-retry-03.log) passes. This is not represented as an uninterrupted
  second ALL PASS run. Runtime CPU **3237 pass** and backend **452 pass** are retained in the check logs.
- Linux packaging/import check completed. [Byte verification](raw/package-source-02.json) compares all
  **143 runtime Python files** in both Worker archive and SDK wheel with `git archive 267ba0b5`.
  Packaging was run at `e496cc18`, whose runtime Python source is unchanged from `267ba0b5`.
- Frozen runtime source archive SHA-256:
  `bf9c44209fc542c551b53fecebfcf9957c3fad30542854fc1beb2c9e65d476cb`.
  Combined remote acceptance archive SHA-256:
  `6ba107eea5c511e2cf2fd31dbabeff1b6c69de2e6abd5d8d13996a1bfdb3361c`.
  Remote manifests were verified before execution and unchanged afterward. Native report records **497**
  files, exact manifest equality and exit codes. Raw archives, manifests, launch receipts and harnesses are
  retained here. No source or receipt from an earlier evidence directory was rewritten.

## What this does NOT show

This closes the listed finite operator, trained parity and source-package checks for `267ba0b5`; it does
not qualify later host/LDSM changes, untested GPU hardware, native installers, managed worker lifecycle,
arbitrary model families or quality/learning behavior. No push, merge, deployment or lab device approval
is established here. No near-80%-vLLM claim is made. Follow-on prototypes have separate evidence.
