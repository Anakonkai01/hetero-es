"""
Loading the pinned Qwen checkpoint and describing it as a `Recipe`: the part that the worker and the coordinator both need.
The logic is the one of `scripts/run_one_candidate.py` (whose evidence, a recipe hash, is pinned below); the checks that need
the real model run only with HETEROES_QWEN_PINNED_PATH and a CUDA GPU, like the other real-model tests.
"""
import os

import pytest
import torch

from heteroes.model.loading import MODEL_ID, PINNED_REVISION, build_recipe, check_noise_selftest, load_pinned_model

PINNED_PATH = os.environ.get("HETEROES_QWEN_PINNED_PATH")
needs_model = pytest.mark.skipif(
    PINNED_PATH is None or not torch.cuda.is_available(),
    reason="set HETEROES_QWEN_PINNED_PATH and use a CUDA GPU to run the real-model checks",
)

# the recipe hash of the evidence of 06/10 (artifacts/regression/2026-10-06-manifest-v1-5070ti): seed 0 is not in a recipe, sigma 1e-3 is
EVIDENCE_RECIPE_HASH = "1604737ea1d7203062d641381172899356a261748f754a8f3264019ac1b3f5b1"


def test_the_pinned_revision_and_model_id_are_the_ones_of_the_contract():
    assert PINNED_REVISION == "7ae557604adf67be50417f59c2c2f167def9a775"
    assert MODEL_ID == "Qwen/Qwen2.5-0.5B-Instruct"


def test_a_directory_that_is_not_the_pinned_revision_is_refused_before_anything_is_loaded(tmp_path):
    wrong = tmp_path / "some-other-checkpoint"
    wrong.mkdir()

    with pytest.raises(ValueError, match=PINNED_REVISION):
        load_pinned_model(wrong, "cpu")


def test_a_path_that_does_not_exist_is_a_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_pinned_model(tmp_path / PINNED_REVISION, "cpu")


def test_the_noise_selftest_passes_on_this_machine():
    check_noise_selftest()


def test_a_machine_that_does_not_generate_the_canonical_noise_is_refused(monkeypatch):
    import heteroes.model.loading as loading

    monkeypatch.setattr(loading, "compute_noise_fingerprint", lambda: "0" * 64)

    with pytest.raises(RuntimeError, match="noise"):
        check_noise_selftest()


@needs_model
def test_the_recipe_of_the_real_model_is_the_recipe_of_the_recorded_evidence():
    loaded = load_pinned_model(PINNED_PATH, "cuda")

    recipe = build_recipe(loaded, sigma=1e-3, eval_dtype="float16")        # the recorded evidence is the FP16 evaluation

    assert recipe.hash == EVIDENCE_RECIPE_HASH
    assert loaded.revision == PINNED_REVISION and recipe.model_revision == PINNED_REVISION == recipe.tokenizer_revision
    assert next(loaded.model.parameters()).dtype == torch.float16 and next(loaded.model.parameters()).device.type == "cuda"
    assert loaded.schema.hash == recipe.schema_hash


@needs_model
def test_the_default_recipe_of_the_real_model_evaluates_in_fp32():
    loaded = load_pinned_model(PINNED_PATH, "cuda")

    recipe = build_recipe(loaded, sigma=1e-3)

    assert recipe.eval_dtype == "float32" and recipe.hash != EVIDENCE_RECIPE_HASH
    assert recipe.hash == build_recipe(loaded, sigma=1e-3, eval_dtype="float32").hash


@needs_model
def test_sigma_and_chunk_size_are_part_of_the_recipe():
    loaded = load_pinned_model(PINNED_PATH, "cuda")

    base = build_recipe(loaded, sigma=1e-3)

    assert build_recipe(loaded, sigma=2e-3).hash != base.hash
    assert build_recipe(loaded, sigma=1e-3, chunk_elements=1024).hash != base.hash


def test_every_choice_of_the_experiment_goes_into_the_recipe_without_a_real_model():
    import torch.nn as nn

    from heteroes.model.loading import LoadedModel
    from heteroes.model.schema import build_parameter_schema

    toy = nn.Linear(3, 3).half()
    loaded = LoadedModel(toy, None, build_parameter_schema(toy), "1" * 40, {"max_new_tokens": 5}, "cpu")
    base = build_recipe(loaded, sigma=1e-3)

    assert (base.sigma, base.chunk_elements, base.reward_eta, base.model_revision) == (1e-3, 262144, 1e-9, "1" * 40)
    assert build_recipe(loaded, sigma=2e-3).sigma == 2e-3
    assert build_recipe(loaded, sigma=1e-3, chunk_elements=1024).chunk_elements == 1024
    assert build_recipe(loaded, sigma=1e-3, reward_eta=1e-8).reward_eta == 1e-8
    assert len({base.hash, build_recipe(loaded, 2e-3).hash, build_recipe(loaded, 1e-3, 1024).hash,
                build_recipe(loaded, 1e-3, reward_eta=1e-8).hash}) == 4
    other_config = LoadedModel(toy, None, loaded.schema, "1" * 40, {"max_new_tokens": 6}, "cpu")
    assert build_recipe(other_config, 1e-3).hash != base.hash                          # the generation config is part of it


# ---------------------------------------------------------------------------
# G7: the noise engine and the workload are choices of the experiment, and each engine has its own self-test
# ---------------------------------------------------------------------------

def toy_loaded():
    import torch.nn as nn

    from heteroes.model.loading import LoadedModel
    from heteroes.model.schema import build_parameter_schema

    toy = nn.Linear(3, 3).half()
    return LoadedModel(toy, None, build_parameter_schema(toy), "1" * 40, {"max_new_tokens": 5}, "cpu")


def test_the_cuda_noise_engine_is_a_choice_of_the_recipe_with_its_own_call_size_and_fingerprint():
    from heteroes.noise.contracts import CUDA_CALL_ELEMENTS, CUDA_ENGINE_VERSION, EXPECTED_CUDA_NOISE_FINGERPRINT

    loaded = toy_loaded()
    cpu = build_recipe(loaded, sigma=1e-3)
    cuda = build_recipe(loaded, sigma=1e-3, noise_engine="cuda")

    assert (cuda.engine_version, cuda.chunk_elements, cuda.noise_fingerprint) == (CUDA_ENGINE_VERSION, CUDA_CALL_ELEMENTS, EXPECTED_CUDA_NOISE_FINGERPRINT)
    assert cuda.hash != cpu.hash and cpu.engine_version != cuda.engine_version


def test_the_cuda_noise_engine_has_no_chunk_size_to_choose():
    with pytest.raises(ValueError, match="call size"):
        build_recipe(toy_loaded(), sigma=1e-3, chunk_elements=1024, noise_engine="cuda")


def test_an_unknown_noise_engine_is_refused():
    with pytest.raises(ValueError, match="noise engine"):
        build_recipe(toy_loaded(), sigma=1e-3, noise_engine="metal")


def test_a_named_workload_goes_into_the_recipe_with_its_own_hash():
    from heteroes.eval.workloads import get_workload

    loaded = toy_loaded()
    default = build_recipe(loaded, sigma=1e-3)
    long = build_recipe(loaded, sigma=1e-3, workload="cot_l3_q32")

    assert default.workload_name == "arith16" and long.workload_name == "cot_l3_q32"
    assert default.workload_hash == get_workload("arith16").hash() and long.workload_hash == get_workload("cot_l3_q32").hash()
    assert default.workload_hash != long.workload_hash and default.hash != long.hash


def test_an_unknown_workload_is_refused():
    with pytest.raises(ValueError, match="workload"):
        build_recipe(toy_loaded(), sigma=1e-3, workload="nope")


def test_the_self_test_that_runs_is_the_one_of_the_engine_of_the_recipe(monkeypatch):
    import heteroes.model.loading as loading

    ran = []
    monkeypatch.setattr(loading, "check_noise_selftest", lambda: ran.append("cpu") or 0.5)
    monkeypatch.setattr(loading, "check_cuda_noise_selftest", lambda device="cuda": ran.append(f"cuda:{device}"))
    loaded = toy_loaded()

    assert loading.check_recipe_selftest(build_recipe(loaded, sigma=1e-3), "cuda") >= 0.0
    assert ran == ["cpu"]
    ran.clear()
    assert loading.check_recipe_selftest(build_recipe(loaded, sigma=1e-3, noise_engine="cuda"), "cuda:0") >= 0.0
    assert ran == ["cuda:cuda:0"]


def test_a_failing_cuda_self_test_is_an_error_for_a_cuda_recipe(monkeypatch):
    import heteroes.model.loading as loading

    def failing(device="cuda"):
        raise RuntimeError("the CUDA noise self-test failed")

    monkeypatch.setattr(loading, "check_cuda_noise_selftest", failing)
    with pytest.raises(RuntimeError, match="self-test"):
        loading.check_recipe_selftest(build_recipe(toy_loaded(), sigma=1e-3, noise_engine="cuda"), "cuda")


def test_the_decode_engine_is_a_choice_of_the_recipe_and_the_long_workloads_default_to_the_compacting_decoder():
    loaded = toy_loaded()
    default = build_recipe(loaded, sigma=1e-3, workload="cot_l1_q128")
    compact = build_recipe(loaded, sigma=1e-3, workload="cot_l1_q128", decode_engine="hf_compact")
    plain = build_recipe(loaded, sigma=1e-3, workload="cot_l1_q128", decode_engine="hf_generate")
    assert default.decode_engine == "hf_compact" and default.hash == compact.hash       # new experiments on a long workload use the compacting decoder unless told otherwise
    assert plain.decode_engine == "hf_generate" and plain.hash != default.hash
    assert build_recipe(loaded, sigma=1e-3).decode_engine == "hf_generate"             # the 16-prompt workload cannot use it
    with pytest.raises(ValueError):
        build_recipe(loaded, sigma=1e-3, workload="arith16", decode_engine="hf_compact")
    with pytest.raises(ValueError):
        build_recipe(loaded, sigma=1e-3, workload="cot_l1_q128", decode_engine="vllm")


def test_the_default_decode_engine_is_a_function_of_the_workload_and_does_not_touch_stored_documents():
    from heteroes import manifest
    assert manifest.default_decode_engine("arith16") == "hf_generate"
    assert all(manifest.default_decode_engine(name) == "hf_compact" for name in manifest.WORKLOAD_NAMES if name != "arith16")
    # a stored recipe document without the key still means the library's generate(), whatever the default of new recipes is
    document = build_recipe(toy_loaded(), sigma=1e-3, workload="cot_l1_q128", decode_engine="hf_generate").to_dict()
    assert "decode_engine" not in document["workload"]
    assert manifest.Recipe.from_dict(document).decode_engine == "hf_generate"
