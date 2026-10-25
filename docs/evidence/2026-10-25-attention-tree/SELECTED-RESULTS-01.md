# Selected source3fd704a5

Exact grouped attention reduction keeps the same arithmetic/reference and error behavior. No precision reduction.

|Model|GPU|B1|B8|B32|
|---|---|---:|---:|---:|
| SmolLM2-360M | 5070 Ti | 277.3 | 1493.9 | 3861.3 |
| SmolLM2-360M | 3060 WSL2 | 169.8 | 735.6 | 1376.2 |
| TinyLlama-1.1B | 5070 Ti | 187.5 | 783.9 | 1804.6 |
| TinyLlama-1.1B | 3060 WSL2 | 101.1 | 281.0 | 574.1 |
| Qwen2.5-0.5B | 5070 Ti | 277.5 | 1386.4 | 3470.5 |
| Qwen2.5-0.5B | 3060 WSL2 | 167.4 | 648.8 | 1181.3 |

Total output token/s, fixed common32-output-token benchmark, median3 synchronized host wall repeats after warmup;
unisolated hosts/builds. B32 remains about23–27% of prior measured vLLM default on5070Ti.

- 452 selected tests pass on each of four GPUs: two5070Ti, Quang3060WSL2 and Thao3060native Windows.
- Full check-all ALL PASS:3038 runtime CPU pass/371 skip,452 backend pass. Six scratch mutants killed after a
  passing control, including padding-zero insertion, left-fold replacement and skipping masked overflow.
- Three trained models, all four parent/candidate/restored states, all three engines, complete consumed-file
  manifests, portable backend identities, prefill hashes, tokens/text/rewards and weight hashes match across
  Linux5070Ti/WSL23060 and against1848d57c. Exact restore. See selected-trained-comparison-01.json.
- Four pinned fixture layouts, both precisions and all states match Linux5070Ti/native Windows3060 exactly;
  native source186-file manifest unchanged,58 audited builds with zero PTX/SASS violations.
- Linux packaging passes; Worker runtime and embedded Server SDK match all nine selected source files. Frozen
  noise/ES/ledger/generation-record paths and the approved plan are unchanged.

## What this does NOT show

No universal/model-quality/native-installer/managed lifecycle qualification or completion of M0–M6. Current strict
remains experimental and inactive as a default. Projection still dominates the new profile; near-vLLM is not met.
No push/merge/deploy, device-state change or learning. Rejected and failed experiments remain immutable.
