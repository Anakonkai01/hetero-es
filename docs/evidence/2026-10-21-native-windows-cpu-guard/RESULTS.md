# Native Windows guarded decoder: PASS

Candidate6 installed Python/runtime on Thao Windows RTX 3060 completed all nine predeclared evaluations
(eight original generation-10 candidates, then repeated c5). The GPU stays FP32 throughout. Full token
arrays, texts/hashes, input IDs/masks, perturbed FP16 and evaluation FP32 weight hashes match the committed
5070 final-source receipts exactly. Recipe/plan/helper identity also matches. Parent restore is exact
after every evaluation. Nine independent in-memory corruption controls are rejected; raw receipts unchanged.

Selective CPU reference calls: `[0, 2, 0, 4, 1, 2, 3, 0, 2]`, 14 total. CPU threads: 20.
Peak GPU allocation: 2.854 GiB. Available physical CPU RAM after each candidate: 46.7–48.9 GiB.
These are diagnostic observations, not a speed, memory-leak or managed-run benchmark.

The installed helper SHA256 is `150ac9fdd1464e6cdb41bbc624173de28f01f53019a04f18b77e178ceb2ea95d`.
No installed runtime file was patched. The probe ran through the candidate6 source and pinned dependencies;
private model/parent input files remain outside Git on D: for possible reproduction. The parent hash was
checked before the probe: `dfbfa65cae82010b068371455d4462b6ad88572788c784d5b5a3f2a52b3a93d9`.

## What this does NOT show

This does not replace the pending fresh 50-generation managed acceptance with audits, a real outage/retry,
and independent re-execution. It does not explain the earlier one-off Windows self-test ACTION_FAILED,
prove a universal margin bound, or establish arbitrary-model compatibility. No learning/speedup claim,
public publication, deployment or live device change.
