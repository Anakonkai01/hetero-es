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

    recipe = build_recipe(loaded, sigma=1e-3)

    assert recipe.hash == EVIDENCE_RECIPE_HASH
    assert loaded.revision == PINNED_REVISION and recipe.model_revision == PINNED_REVISION == recipe.tokenizer_revision
    assert next(loaded.model.parameters()).dtype == torch.float16 and next(loaded.model.parameters()).device.type == "cuda"
    assert loaded.schema.hash == recipe.schema_hash


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
