# Extensibility — LoRA weight space

Baseline: `0076900` (subset receipts), branch `feat/extensibility-step0`. The owner allowed installing PEFT (2026-10-19).
Implements the LoRA part of ADR-008 section 4 (draft) in a new module, `runtime/src/heteroes/model/lora.py`. `noise/`,
`es/`, `ledger/` and `generation_record.py` are unchanged; nothing in the product attaches adapters yet.

## Environment change

`pip install peft==0.21.2` in the Conda environment `heteroes-match` only. A `pip freeze` before and after differs by
exactly one line (`peft==0.21.2`): no other package was installed or upgraded (transformers 5.17.0, torch 2.13.0+cu132
unchanged). The Conda `ai` environment, the backend venv and the desktop worker profile
(`desktop/worker/resources/requirements-*.txt`, hash-pinned) were not changed: adding PEFT to the installers is r11 work.
Recorded in `runtime/pyproject.toml` (extra `lora`) and `runtime/THIRD_PARTY.md` (Apache-2.0, from the package metadata).

## What changed

- `attach_lora(model, space, seed)`: injects FP16 LoRA adapters (PEFT `inject_adapter_in_model`, dropout 0, no bias, no
  rsLoRA/DoRA) into an FP16 base, initialized from `seed` without consuming the caller's random state.
- `trainable_schema(model)`: the subset schema of the `lora_A`/`lora_B` tensors (the subset mechanism of the previous
  step), so the unchanged ES code perturbs, restores, updates, hashes and publishes only the adapters.
- `create_initial_adapter` / `load_adapter_`: the initial adapter is a weights file named by its SHA-256; a worker loads it
  over its own adapters, and a wrong hash is refused before anything is copied.
- `export_peft`: writes `adapter_config.json` + `adapter_model.safetensors` for `PeftModel.from_pretrained`; nothing is
  written when the model has no adapters.

## What the tests show (`runtime/tests/model/test_lora_space.py`, tiny Qwen2 built from a config, CPU)

- 8 FP16 adapter tensors (2 layers × q/v × A/B); B starts at 0 and the adapted model gives the base model's outputs.
- Perturbation, restore and update leave every base tensor bit-identical; one perturbation already changes the outputs
  (σ·ε_B·A is first order), restore gives the outputs back exactly.
- The initial adapter file is identical for the same seed, different for another seed; a worker with other adapters loads
  it to bit-identical weights and outputs.
- The PEFT export, loaded by `PeftModel.from_pretrained` on a fresh base, gives the same logits (atol 1e-5, FP32 forward)
  as our model after a perturbation, and records the base model id.

## Receipts

| Check | Result | File |
| --- | --- | --- |
| Full CPU product check | 22/22 PASS; runtime 2,175 passed (7 new), 100 skipped; backend 287 passed | `check-all.log`, `checks/` |
| Mutation check | control passes; 8/9 killed | `lora-mutants.json`, `lora-mutation.log` |

**Equivalent mutant:** removing the explicit FP16 cast of the adapters survives because PEFT 0.21.2 already creates the
adapter layers in the base layer's dtype (FP16). The cast stays as a guard if a later PEFT changes that default; with the
pinned version it changes nothing.

## What this does NOT show

No real Qwen 0.5B model, no GPU or CUDA noise engine with adapters, no worker or coordinator using LoRA, no Windows, and no
learning result: whether ES on LoRA learns, and how it compares with full-parameter ES, is an experiment still to run.
