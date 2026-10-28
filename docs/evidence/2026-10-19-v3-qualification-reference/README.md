# desktop-v3 qualification reference with a pinned adapter — 2026-10-19

Handoff `docs/handoff-v3-audit-recovery.md` section 5 step 2. Code: commit `e2d6c32`
(`product/qualification_v3.py`, `v3/local.py` `initial_adapter=`, `scripts/build_v3_reference.py`).

## Design

Follows `../2026-10-19-v3-lora-cross-os`: the same adapter seed gives different bytes on native
Windows, so a worker never makes an adapter. The reference holds:

- `cells.full`: a full-parameter Recipe v3 (sigma 0.001) and `cells.lora`: LoRA rank 4, alpha 8,
  q_proj/v_proj (sigma 0.02, because `lora_B` starts at zero). FP32 evaluation, CPU noise engine,
  HF generate, 32 new tokens, 4 prompts, declarative `last-integer` scorer.
- For each cell the recipe and plan, and for the positive AND negative antithetic candidate the recipe
  hash, model-manifest hash, parent/perturbed/restored weight hashes, the hash of the raw texts and the reward.
- `adapter`: the file name and SHA-256 of the pinned initial adapter, shipped beside the JSON.

`qualify` checks the profile, PEFT 0.21.2 and the adapter file hash first, rebuilds each cell's documents on
the device (they must equal the reference's), runs each signed candidate twice, requires identical repeats,
exact restore and equality with the reference, and returns `recipeVersions: [3]`, `runtimeProfile:
desktop-v3`, `compatibility.recipeV3` (full), `compatibility.recipeV3Lora` and the adapter hash.

## Results

- `reference/`: built by `build_v3_reference.py --gpu --adapter-seed 7` on this machine's RTX 5070 Ti
  (Linux, Torch 2.13.0+cu132). The adapter made on Linux from seed 7 is
  `051b79e34551eddac13dc3029743c32418bb332b3947b5b6b1249c9145e86b1e`, the same bytes as the earlier
  Linux GPU runs. Positive and negative texts differ in both cells; rewards full 0/0, LoRA 0.5/0.
- `windows-3060-first.json`: **native Windows RTX 3060 QUALIFIED** (CPython 3.12.15, Torch 2.13.0+cu132,
  isolated PEFT, existing pinned interpreter/model read-only, source `git archive e2d6c32`, tar SHA-256
  `08fdbb6b709d929e7c33d187dfd63064f0e96c43a941a4dfbfdf86cdf940d0e8`, new private folder
  `%LOCALAPPDATA%/HeteroES-v3-20261019/qual-e2d6c32`). `coordinator: false`.
- `5070ti-qualify.json`: a second, independent process on the 5070 Ti also qualifies. Its `recipeV3` and
  `recipeV3Lora` evidence is identical to the Windows one.
- Model-manifest hash `af52722f…` equals `study.data.sha(study.models.inspect(...))` for the pinned Qwen
  snapshot, the hash the backend registers for a model.
- Tests (`targeted-tests.log`): tiny-model round trip; drift of a text, the adapter file, the plan or the
  profile is refused; `create_initial_adapter` is patched to fail during qualification; builder GPU gate,
  Linux-only seed adapters and the GPU device. Mutations (`mutation/`): 11 + 4 mutants; one survivor
  (profile not checked) got a test and was then killed; builder survivor (device) likewise. All killed.

## What this does NOT show

- Not wired yet: `qualification.main`, the desktop setup/service, profile generation and backend admission
  are unchanged (handoff steps 3–5). Nothing here admits a device.
- Two GPUs (5070 Ti Linux, 3060 native Windows) and one model; not the 1660S, not other drivers.
- The Windows side reuses an existing interpreter plus an isolated dependency folder, not a fresh installer.
- A qualification compares two short candidates per cell; it is a compatibility gate, not learning evidence.
- The tiny-model references in the tests prove the mechanism only and are never shipped.
