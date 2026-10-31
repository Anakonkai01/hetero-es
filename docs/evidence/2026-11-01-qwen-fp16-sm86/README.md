# RTX 3060 FP16 arithmetic reference

Captured on 2026-11-01 from an independent Hugging Face greedy loop on the retained pinned Qwen2.5-0.5B-Instruct model.
The script uses the workload constants but does not call the runtime generation or candidate functions.

The 16 outputs have reward 0.25. Compared with the immutable 2026-09-29 RTX 5070 Ti probe, question index 5 is `674`
rather than `664`; every other text is equal. This is the non-strict FP16 architecture sensitivity already described
in numerical-contract sections 15 and 17. It does not alter canonical noise, perturbation, restore or update identity.
The two failing WSL tests had incorrectly required the 5070 Ti FP16 text on every GPU. The new reference preserves
exact text, prediction and reward assertions on each measured device; it does not accept arbitrary alternatives.

The JSON records the actual GPU, compute capability, Python/PyTorch/Transformers versions, workload hash and model-file
SHA-256. Tests must still fail if output changes on either measured GPU. Unknown GPUs have no reference and fail clearly.

## What this does NOT show

This is not strict cross-GPU inference, universal FP16 portability, model improvement, or a learning result. It covers one
pinned model, workload and software stack on the RTX 3060. It does not certify a different SM86 GPU merely by capability.
