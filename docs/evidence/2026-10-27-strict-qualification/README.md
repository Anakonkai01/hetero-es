# M4 model qualification keyed by decoder (`strict_b22_v1`), 2026-10-27

Slice `8d52b76c` made the lab's model qualification depend on the decoder: `qualification_key(engine, decoder)` is the
noise engine, or `<engine>+strict_b22_v1` for the strict identity. A strict reference is built by the device with the
strict decoder (FP16, live weights) and cannot pass as a plain reference, and the other way round. The device agent keeps
`noiseEngineVersion` and `decoder` in the frozen probe command. The lab accepts `evalDtype` only for the strict decoder
and checks strict qualification per selected device. This folder holds the mutation check of that slice and of the
lab UI that uses it.

## Tests added by the mutation check

The first run left 7 mutants alive (runtime 3 of 14, backend 4 of 16); each pointed at a missing test:

- `test_child_builds_the_reference_for_the_commanded_engine_and_decoder` (the probe child forwards engine and decoder);
- a pending strict probe does not block a plain first probe, and the other way round
  (`test_a_pending_probe_blocks_only_probes_of_the_same_reference`);
- a profile without per-engine hashes never qualifies for the strict decoder;
- a plain experiment keeps its document without `evalDtype`, and a strict one submits `evalDtype: float16` to the
  runtime (`test_a_plain_experiment_keeps_its_document_and_a_strict_one_submits_fp16`).

One runtime mutant ("check_reference accepts any decoder") was removed as **equivalent**: with the early check gone, an
unknown decoder is still refused two lines later by `cell_configs`/`_documents` (only the message differs).

## Results

| Group | File | Killed |
| --- | --- | ---: |
| runtime (`tests/v3/test_model_qualification.py`, `test_model_probe_process.py`, `tests/ledger/test_model_probe_agent.py`; GPU opt-in so the tiny-model round trip runs) | [mutation-runtime.log](checks/mutation-runtime.log) | 13 of 13 |
| backend (`backend/tests/test_model_qualification.py`) | [mutation-backend.log](checks/mutation-backend.log) | 16 of 16 |

Registered as `mutation-strict-qualification-runtime` and `-backend`; gate `M4.qualification` now needs them and
`check-all` (which includes the browser checks of the lab UI below).

## Lab UI (same session)

- Experiment form: Recipe v3 offers the decoder `strict_b22_v1` ("Strict FP16, bit-exact on every GPU"); choosing it
  sends `evalDtype: "float16"` (no other run sends the field).
- Models page: a "Decoder" choice beside the noise engine; the strict choice forces the new engine, shows the strict
  readiness of the selected computer and starts the check with `decoder: "strict_b22_v1"`.
- Browser checks (fixture lab, Chromium): `check-web-model-qualification.mjs` starts a strict check through the UI and reads
  `decoder` and the engine from the command the device receives; `check-web-experiments.mjs` selects the strict decoder, sees
  the request carry FP16, sees the lab refuse a device without the strict check, and saves a plain draft without
  `evalDtype`. Vietnamese strings added; `check-i18n` is clean.

## What this does NOT show

No real strict reference was built or compared on a GPU through the lab (the GPU round trip is the tiny model with
`HETEROES_GPU_ACCEPTANCE=1`, locally); the browser checks use a CPU fixture lab. A strict experiment has not been run
end to end: that is M5 (`acceptance/probes/strict_e2e.py`, not yet run). `strict_b22_v1` is still not the default for new
GPU runs (`M4.default` is open).
