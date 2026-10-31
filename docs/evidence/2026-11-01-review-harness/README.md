# A-024 / A-025 acceptance harness corrections

Source fix: a5d81cbd. Package bytes now require a clean source tree using the same source identity policy as receipts:
docs/, runtime/docs/ and root Markdown are excluded. The actual Worker and Server SDK runtime bytes still must exactly
equal git archive HEAD runtime/src. Seven tests use isolated Git repositories and actual tar/wheel archives, including
modified/untracked source and mismatched package bytes. The original real Linux package build succeeded before its old
documentation guard refused it; that intermediate failure is archived separately.

Non-strict HF FP16 tests now choose the original immutable RTX 5070 Ti probe or the independently recorded RTX 3060
reference. The test never accepts arbitrary alternative strings. Unknown GPUs fail explicitly. Exact text, prediction,
reward, weight, perturbation, restore and repeatability checks remain. The strict cross-GPU golden files are unchanged.
The SM86 capture and its immutable fixture copy are in 2026-11-01-qwen-fp16-sm86. Three CPU selector tests cover the
original reference, the one measured difference and refusal of unmeasured devices. Passed-count floors were increased
to 1,639 local, 1,560 WSL and 572 noise/ES (no skip allowance was added).

Validation: 58 acceptance selftests passed; 45 candidate/generation CPU regressions passed with 12 intentional GPU skips
(CUDA_VISIBLE_DEVICES was empty). Mutation control: 10 passed; all six targeted mutants killed. The fixture checker
verified all 16 archive copies byte-for-byte. A006-archive-links.json verifies 17 repaired Markdown evidence links
against immutable evidence-archive blobs.

## What this does NOT show

These focused checks do not replace the full new-source CPU/GPU/performance/fault/package/mutation and three-host
acceptance. The prior matrix's green checks belong to src-c0d90ddb, not this fix. No live lab was deployed or changed.
