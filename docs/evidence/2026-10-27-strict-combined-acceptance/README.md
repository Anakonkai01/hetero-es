# Combined strict B22 scheduling acceptance, 2026-10-27

Frozen runtime **`0eb86cb948878fe430049882b80b3a5ad74730ba`**, against `267ba0b5`. This combines the bounded
host work (`5c2f849c`), SM120 B22 ldmatrix input loads (`eebf689f`) and SM120 B22 balanced split-K waves
(`0eb86cb9`). SM86 keeps scalar activation loads and its preceding split plan. These are execution changes
to the same B22 integer products/rounding and strict FP32 nonlinearities.

## Whole generation results

Qwen B32, prefix reuse off, greedy generation, unchanged token hashes. Each value is the mean of two
independent five-sample round medians in the ABAB processes, in token/s.

| Host | short32 before | after | gain | chat128 before | after | gain |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 5070 Ti Linux | 9392.7 | 9866.1 | 5.04% | 9557.0 | 9889.8 | 3.48% |
| 3060 WSL2 | 2977.3 | 3055.0 | 2.61% | 2899.2 | 2900.9 | 0.06% |
| 3060 native Windows | 3005.1 | 3035.7 | 1.02% | 2888.3 | 2906.4 | 0.63% |

The primary short32 ratio is **71.3%** of the established vLLM control, 13834.6 token/s. An 80% result
would be approximately 11068 token/s; the goal remains open. The very small WSL chat128 difference is
not a robust speedup claim. Timings from different evidence rounds are not added together as gains.

## Verification

- Frozen complete selected source suites: Linux/5070 Ti **1075 pass**, 1028.42 s; WSL2/3060 **1075 pass**,
  940.67 s; native Windows/3060 **917 pass**, 1236.57 s. Native selects a different suite from Linux. Its
  one retained warning is pytest's already-imported `anyio` assertion-rewrite warning, not a numerical failure.
- Qwen, Smol and Tiny trained parent/canonical perturbation pairs/exact restore match on Linux and WSL2,
  and match the preceding sealed `267ba0b5` cases. Qwen also matches native Windows, including the same
  real EOS controls. Trained native Smol/Tiny were not run. [verify.py](harness/verify.py) produces
  [summary-01.json](raw/summary-01.json), checking source manifests, canonical outputs and every timing hash.
- **4/4 CPU mutants** kill incorrect wave rounding, K rounding, workspace caps and repeated-projection
  accounting. **4/4 GPU/host mutants** kill the wrong upper-K fragment, missing input row half, mismatched
  shared swizzle and an inverse cache keyed by the wrong precision. Controls pass; see the two mutation logs.
  The preceding bounded-head implementation's 10 mutants were separately checked at `267ba0b5`; they are
  not represented as new mutation runs here.
- **check-all ALL PASS**, including runtime CPU **3252 pass / 942 skip**, backend **452 pass**, formatting,
  source imports, frontend/desktop units/types/builds and fixture browser/Electron checks. Later changes
  before sealing were evidence/documentation only; no runtime source changed after the frozen commit.
- Linux packaging/import checks pass. [Package byte verification](raw/package-source-01.json) checks all
  **143 runtime Python files** in the actual packaged Worker archive and the SDK wheel embedded in the
  packaged Server archive against `git archive 0eb86cb9`. The packaging receipt records `b64cc433`, an
  evidence-only successor with identical runtime source. No pinned package resource or public download
  was replaced.
- PTX/SASS audits, including the new nonpower split variants, run in the complete suites for
  SM80/86/89/90/120. Only SM86 and SM120 have hardware execution evidence. The new SM120 route is exercised
  on Linux; native SM120 code generation is not native SM120 hardware qualification.

Remote archive SHA-256: `c769e6350080ee3f0e102a0fe1aea6b082d5f519f648323b256fa16d6e5c4e79`.
Manifests match before execution and remain unchanged afterward. The native archive contains **6275 files**:
this stage uses the full `git archive runtime` for both source versions, including retained artifacts,
rather than the earlier source/tests-only stage. All raw receipts and controller/harness sources are kept.

The post-acceptance controller also launches independent operator research only after the local suite
exits. Its reciprocal/occupancy outputs live in separate directories and do not form part of this selected
runtime or its measured combined speedup.

## What this does NOT show

No near-80% result, arbitrary input/model/perturbation qualification, learning result, managed lifecycle,
native installer or GPU execution of installed packages is established. No deployment, push, merge, lab
approval or contribution state changed. Standalone operator experiments are not selected by these gates.
