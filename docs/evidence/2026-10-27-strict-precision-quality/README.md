# Finite B14/B22 output and candidate survey, 2026-10-27

This is arithmetic research under the approved separate-backend plan, not a change to the B22 performance
goal. One primary FP16 Qwen model is shared by two engines. Each of 64 fixed chat questions is generated
with EOS enabled and a 512-token limit for the parent, seeds 7001–7004 at ±0.001 with canonical ENGINE_V2,
and the exactly restored parent. There is **no ES update or learning run**. Weight/schema/model/workload
hashes and every token/text/finish reason are retained; any inference/restore error aborts the probe.

The local 5070 Ti uses the fast B14 conversion prototype; the 3060 WSL2 uses the frozen `267ba0b5` original
B14 implementation. [Parity receipt](raw/parity-5070ti-3060-01.json) verifies the same model/input/candidate
weights and **identical full outputs across both GPUs for each precision**, all **640 rows per precision**.
This also provides finite old-versus-fast B14 equivalence. It does not imply equivalence between B14 and B22.

Using the existing tested impact scorer, the 3060 survey excluding the repeated restored parent gives
**5 reward flips / 576 answers** between B22 and B14. Every candidate's correct count differs by at most
one question (**1.5625 percentage points**); the best-candidate index set remains `[6]`. Parent correct
counts are **31/64 versus 30/64**. Token differences occur on 3–9 rows per candidate; full per-case counts,
truncations and metrics are in [summary-3060-01.json](raw/summary-3060-01.json). Ties and hypothetical ES
coefficients do change: merged-coefficient cosine is about **0.948** for z-score and **0.878** for rank.
An unchanged best-candidate set does not establish an unchanged ES direction. Truncated rows remain
reported, not silently scored as completed parity. These observations are not an ES-learning conclusion.

## What this does NOT show

Native Windows quality parity, arbitrary prompts, all perturbation magnitudes, broad quality acceptance,
learning behavior and managed/native installer qualification remain unproven. B14 does change some B22
tokens and rewards; it is not selected to satisfy a goal that preserves B22 bits/tokens/flags. Historical
recipes, defaults, device approval and live lab processes are unchanged.
