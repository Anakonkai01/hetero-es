import copy
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pytest

from heteroes import manifest
from heteroes.canonical import canonical_json_hash
from heteroes.manifest import (
    MANIFEST_VERSION,
    MAX_SEED,
    CandidateDescriptor,
    Recipe,
    derive_seed,
    effective_generation_config,
    generation_config_sha256,
)
from heteroes.noise.contracts import ENGINE_VERSION
from heteroes.noise.selftest import EXPECTED_NOISE_FINGERPRINT

REVISION = "7ae557604adf67be50417f59c2c2f167def9a775"
SCHEMA = "0b21250e331398a266785dc473da3a8b8f5e8f98fa15e9044637d742eb7845ec"
WORKLOAD = "cad822bc1e65a9ec37d948e5415cff22c70f96500e2043e6299bbdd5cea0b8d5"
GENERATION_CONFIG = {"do_sample": True, "temperature": 0.7, "top_k": 20, "top_p": 0.8, "repetition_penalty": 1.1,
                     "pad_token_id": 151643, "bos_token_id": 151643, "eos_token_id": [151645, 151643]}
EVIDENCE = Path(__file__).resolve().parents[1] / "artifacts" / "regression"
RECORDS = [EVIDENCE / "2026-10-05-one-candidate" / "5070ti.json",
           EVIDENCE / "2026-10-06-cross-machine-one-candidate" / "1660s.json"]


def make_recipe(**changes):
    values = dict(
        model_id="Qwen/Qwen2.5-0.5B-Instruct", model_revision=REVISION, tokenizer_revision=REVISION,
        dtype="torch.float16", schema_hash=SCHEMA, engine_version=ENGINE_VERSION, chunk_elements=262144,
        noise_fingerprint=EXPECTED_NOISE_FINGERPRINT, sigma=0.001, reward_eta=1e-9, workload_hash=WORKLOAD,
        generation_config_sha256=generation_config_sha256(GENERATION_CONFIG),
        eval_dtype="float16",      # the v1 evidence is FP16; the default of a new recipe is FP32 (O8), tested at the end of this file
    )
    values.update(changes)
    return Recipe(**values)


def make_descriptor(**changes):
    values = dict(recipe_hash=make_recipe().hash, parent_weights_sha256="c" * 64, experiment_id="regression",
                  generation=0, index=0, seed=0)
    values.update(changes)
    return CandidateDescriptor(**values)


# ---------------------------------------------------------------------------
# the recipe
# ---------------------------------------------------------------------------

def test_the_recipe_document_has_exactly_the_agreed_shape():
    document = make_recipe().to_dict()

    assert set(document) == {"manifest_version", "model", "noise", "perturbation", "update", "workload"}
    assert document["manifest_version"] == MANIFEST_VERSION == 1
    assert set(document["model"]) == {"id", "revision", "tokenizer_revision", "dtype", "schema_hash"}
    assert set(document["noise"]) == {"engine_version", "chunk_elements", "fingerprint"}
    assert document["update"] == {
        "epsilon": "canonical_fp16_upcast_fp32", "accumulation_dtype": "float32",
        "reward_standardization": "population_std_float64_zero_below_eta", "candidate_order": "listed_order",
        "reward_eta": 1e-9}
    assert document["perturbation"] == {"sigma": 0.001, "sigma_float32": float(np.float32(0.001))}
    assert float(np.float32(0.001)) != 0.001   # premise: 1e-3 is not exact, the float32 value is a different number


def test_the_recipe_hash_is_pinned():
    # Regression guard, produced by this code: any change of a field or of the serialization shows here.
    assert make_recipe().hash == canonical_json_hash(make_recipe().to_dict())
    assert make_recipe().hash == PINNED_RECIPE_HASH


PINNED_RECIPE_HASH = "1604737ea1d7203062d641381172899356a261748f754a8f3264019ac1b3f5b1"   # regression guard produced by this code on 2026-10-06


@pytest.mark.parametrize(
    "change",
    [
        dict(model_id="Qwen/Other"), dict(model_revision="1" * 40), dict(tokenizer_revision="1" * 40),
        dict(schema_hash="1" * 64), dict(chunk_elements=1024), dict(noise_fingerprint="1" * 64),
        dict(sigma=0.002), dict(reward_eta=1e-8), dict(workload_hash="1" * 64),
        dict(generation_config_sha256="1" * 64),
    ],
)
def test_changing_any_field_changes_the_recipe_hash(change):
    assert make_recipe(**change).hash != make_recipe().hash


def test_the_recipe_hash_is_the_same_when_built_twice_and_when_read_back_from_json():
    recipe = make_recipe()
    again = Recipe.from_dict(json.loads(json.dumps(recipe.to_dict())))

    assert again == recipe and again.hash == recipe.hash == make_recipe().hash


@pytest.mark.parametrize(
    "change, error",
    [
        (dict(model_revision="main"), ValueError), (dict(model_revision="A" * 40), ValueError),
        (dict(schema_hash="abc"), ValueError), (dict(noise_fingerprint=""), ValueError),
        (dict(dtype="torch.bfloat16"), ValueError), (dict(engine_version="numpy_pcg64_v9"), ValueError),
        (dict(chunk_elements=0), ValueError), (dict(chunk_elements=-5), ValueError),
        (dict(chunk_elements=1.5), TypeError), (dict(chunk_elements=True), TypeError),
        (dict(sigma=0.0), ValueError), (dict(sigma=-1e-3), ValueError), (dict(sigma=float("nan")), ValueError),
        (dict(sigma=float("inf")), ValueError), (dict(sigma="0.001"), TypeError), (dict(sigma=True), TypeError),
        (dict(reward_eta=0.0), ValueError), (dict(reward_eta=float("nan")), ValueError),
        (dict(model_id=""), ValueError), (dict(model_id=None), TypeError),
        (dict(workload_hash=123), TypeError),
    ],
)
def test_an_invalid_recipe_is_refused(change, error):
    with pytest.raises(error):
        make_recipe(**change)


@pytest.mark.parametrize(
    "operational", ["worker_id", "attempt_id", "lease_token", "retry", "reward", "numpy_version", "torch_version"])
def test_the_recipe_has_no_operational_or_version_fields(operational):
    # Noise identity must not depend on operational metadata; library versions are checked by behaviour instead.
    with pytest.raises(TypeError):
        make_recipe(**{operational: 1})


def test_the_recipe_is_immutable():
    with pytest.raises(Exception):
        make_recipe().sigma = 0.5


def test_from_dict_refuses_documents_that_do_not_match_the_format():
    good = make_recipe().to_dict()
    cases = {}
    cases["missing key"] = {k: v for k, v in good.items() if k != "update"}
    cases["extra key"] = {**good, "worker": "w1"}
    cases["extra nested key"] = {**good, "noise": {**good["noise"], "numpy": "2.4.5"}}
    cases["other version"] = {**good, "manifest_version": 2}
    cases["sigma_float32 disagrees"] = {**good, "perturbation": {"sigma": 0.001, "sigma_float32": 0.001}}
    cases["update label changed"] = {**good, "update": {**good["update"], "accumulation_dtype": "float16"}}
    for name, document in cases.items():
        with pytest.raises(ValueError):
            Recipe.from_dict(document)


# ---------------------------------------------------------------------------
# the generation config: the set values decide
# ---------------------------------------------------------------------------

def test_effective_generation_config_drops_none_and_the_library_version():
    raw = {**GENERATION_CONFIG, "max_length": None, "use_mtp": None, "transformers_version": "5.17.0"}

    assert effective_generation_config(raw) == GENERATION_CONFIG


def test_two_library_versions_give_the_same_generation_config_hash_and_a_changed_setting_does_not():
    older = {**GENERATION_CONFIG, "transformers_version": "5.5.0"}
    newer = {**GENERATION_CONFIG, "max_cache_len": None, "use_mtp": None, "transformers_version": "5.17.0"}

    assert generation_config_sha256(older) == generation_config_sha256(newer)
    assert generation_config_sha256({**GENERATION_CONFIG, "repetition_penalty": 1.0}) != generation_config_sha256(older)
    assert generation_config_sha256({**GENERATION_CONFIG, "eos_token_id": [151645]}) != generation_config_sha256(older)


def test_the_order_of_the_keys_of_the_generation_config_does_not_matter():
    reordered = dict(reversed(list(GENERATION_CONFIG.items())))

    assert generation_config_sha256(reordered) == generation_config_sha256(GENERATION_CONFIG)


# ---------------------------------------------------------------------------
# the real evidence: the two machines build the same recipe
# ---------------------------------------------------------------------------

def recipe_from_record(record, with_numpy_version=False):
    run = record["runs"][0]
    recipe = make_recipe(
        model_revision=record["model"]["revision"], tokenizer_revision=record["model"]["tokenizer_revision"],
        dtype=record["model"]["dtype"], schema_hash=run["schema_hash"], engine_version=run["engine_version"],
        chunk_elements=run["chunk_elements"], sigma=run["sigma"], workload_hash=run["workload_hash"],
        generation_config_sha256=generation_config_sha256(record["model"]["generation_config"]),
    )
    if not with_numpy_version:
        return recipe.hash
    return canonical_json_hash({**recipe.to_dict(), "numpy": record["environment"]["numpy"]})


@pytest.mark.skipif(not all(path.exists() for path in RECORDS), reason="evidence files not found")
def test_the_recipes_of_the_5070ti_and_the_1660s_records_have_the_same_hash():
    a, b = (json.loads(path.read_text(encoding="utf-8")) for path in RECORDS)

    assert recipe_from_record(a) == recipe_from_record(b) == make_recipe().hash


@pytest.mark.skipif(not all(path.exists() for path in RECORDS), reason="evidence files not found")
def test_a_numpy_version_in_the_recipe_would_have_split_the_two_compatible_machines():
    # Why the recipe has a noise fingerprint and no NumPy version: the two machines run NumPy 2.4.5 and 2.5.2
    # and generate identical noise, so the version string would only have produced a false mismatch.
    a, b = (json.loads(path.read_text(encoding="utf-8")) for path in RECORDS)

    assert a["environment"]["numpy"] != b["environment"]["numpy"]
    assert recipe_from_record(a, with_numpy_version=True) != recipe_from_record(b, with_numpy_version=True)


# ---------------------------------------------------------------------------
# the candidate descriptor
# ---------------------------------------------------------------------------

def test_the_descriptor_document_and_candidate_id():
    descriptor = make_descriptor(experiment_id="exp-1", generation=3, index=5, seed=42)

    assert descriptor.to_dict() == {
        "recipe_hash": make_recipe().hash, "parent_weights_sha256": "c" * 64, "experiment_id": "exp-1",
        "generation": 3, "index": 5, "seed": 42}
    assert descriptor.candidate_id == "exp-1/g3/c5"
    assert CandidateDescriptor.from_dict(json.loads(json.dumps(descriptor.to_dict()))) == descriptor


def test_the_candidate_id_does_not_depend_on_the_seed_or_the_parent():
    # The logical job is (experiment, generation, index); a retry or another worker never changes it.
    assert make_descriptor(seed=1).candidate_id == make_descriptor(seed=2).candidate_id
    assert make_descriptor(parent_weights_sha256="d" * 64).candidate_id == make_descriptor().candidate_id


@pytest.mark.parametrize(
    "operational", ["worker_id", "attempt_id", "lease_token", "lease_deadline", "retry", "reward", "arrival_time"])
def test_the_descriptor_refuses_operational_fields(operational):
    with pytest.raises(TypeError):
        make_descriptor(**{operational: 1})
    with pytest.raises(ValueError):
        CandidateDescriptor.from_dict({**make_descriptor().to_dict(), operational: 1})


@pytest.mark.parametrize(
    "change, error",
    [
        (dict(seed=-1), ValueError), (dict(seed=MAX_SEED), ValueError), (dict(seed=2**200), ValueError),
        (dict(seed=1.0), TypeError), (dict(seed=True), TypeError), (dict(seed="1"), TypeError), (dict(seed=None), TypeError),
        (dict(generation=-1), ValueError), (dict(generation=0.5), TypeError), (dict(index=-1), ValueError),
        (dict(index=False), TypeError), (dict(experiment_id=""), ValueError), (dict(experiment_id="a/b"), ValueError),
        (dict(experiment_id="a b"), ValueError), (dict(experiment_id=5), TypeError),
        (dict(recipe_hash="abc"), ValueError), (dict(parent_weights_sha256="C" * 64), ValueError),
    ],
)
def test_an_invalid_descriptor_is_refused(change, error):
    with pytest.raises(error):
        make_descriptor(**change)


def test_the_largest_allowed_seed_is_below_2_to_the_53():
    assert make_descriptor(seed=MAX_SEED - 1).seed == 2**53 - 1
    assert MAX_SEED == 2**53 == 9007199254740992   # integers below this survive a read by JavaScript


def test_the_descriptor_keeps_a_plain_int_so_that_json_can_write_it():
    # The update accepts NumPy integers (contract section 3); a descriptor must be written to JSON, so the caller converts.
    with pytest.raises(TypeError):
        make_descriptor(seed=np.int64(7))
    descriptor = make_descriptor(seed=int(np.int64(7)))

    assert type(descriptor.seed) is int and json.dumps(descriptor.to_dict())


# ---------------------------------------------------------------------------
# derive_seed: the coordinator's way of choosing, not a contract between machines
# ---------------------------------------------------------------------------

def test_derive_seed_matches_a_hand_written_oracle():
    expected = int.from_bytes(hashlib.sha256(b"heteroes-seed-v1|exp-1|3|5").digest()[:8], "little") & (2**52 - 1)

    assert derive_seed("exp-1", 3, 5) == expected
    assert expected == PINNED_DERIVED_SEED


PINNED_DERIVED_SEED = 318747854069555   # regression guard produced by this code on 2026-10-06


def test_derive_seed_is_repeatable_and_changes_with_every_input():
    base = derive_seed("exp-1", 3, 5)

    assert derive_seed("exp-1", 3, 5) == base
    assert len({base, derive_seed("exp-2", 3, 5), derive_seed("exp-1", 4, 5), derive_seed("exp-1", 3, 6)}) == 4


def test_the_seeds_of_many_generations_are_distinct_and_below_the_limit():
    seeds = [derive_seed("exp-1", g, i) for g in range(300) for i in range(64)]

    assert len(set(seeds)) == len(seeds)
    assert max(seeds) < 2**52 < MAX_SEED
    assert all(0 <= s for s in seeds)


def test_every_generation_has_new_noise_unlike_a_fixed_list():
    first = [derive_seed("exp-1", 0, i) for i in range(8)]
    second = [derive_seed("exp-1", 1, i) for i in range(8)]

    assert not set(first) & set(second)


@pytest.mark.parametrize("bad", [dict(experiment_id=""), dict(experiment_id="a/b"), dict(generation=-1),
                                 dict(index=-1), dict(generation=1.0), dict(index=True)])
def test_derive_seed_refuses_bad_arguments(bad):
    arguments = dict(experiment_id="exp-1", generation=0, index=0)
    arguments.update(bad)

    with pytest.raises((ValueError, TypeError)):
        derive_seed(**arguments)


def test_a_derived_seed_makes_a_valid_descriptor():
    assert make_descriptor(seed=derive_seed("regression", 0, 0)).seed == 2012071010219947


# ---------------------------------------------------------------------------
# G6: the precision of the forward pass of the evaluation is part of the recipe (optional: absent means FP16 and keeps the v1 hash)
# ---------------------------------------------------------------------------

def test_an_fp16_evaluation_leaves_the_v1_document_and_hash_exactly_as_they_were():
    assert make_recipe().eval_dtype == "float16"
    assert "eval_dtype" not in make_recipe().to_dict()["workload"]
    assert make_recipe(eval_dtype="float16").hash == PINNED_RECIPE_HASH


def test_an_fp32_evaluation_is_another_recipe_with_its_own_hash_and_a_label_in_the_workload():
    recipe = make_recipe(eval_dtype="float32")
    assert recipe.to_dict()["workload"]["eval_dtype"] == "float32"
    assert recipe.hash != PINNED_RECIPE_HASH and recipe.hash != make_recipe(eval_dtype="float16").hash


def test_an_fp32_recipe_round_trips_through_json():
    recipe = make_recipe(eval_dtype="float32")
    again = Recipe.from_dict(json.loads(json.dumps(recipe.to_dict())))
    assert again == recipe and again.hash == recipe.hash and again.eval_dtype == "float32"


@pytest.mark.parametrize("bad", ["bfloat16", "float64", "fp32", "", None, 32])
def test_an_unknown_evaluation_precision_is_refused(bad):
    with pytest.raises((ValueError, TypeError)):
        make_recipe(eval_dtype=bad)


def test_a_document_that_says_float16_explicitly_is_refused_because_the_default_is_written_by_leaving_it_out():
    document = make_recipe().to_dict()
    document["workload"]["eval_dtype"] = "float16"                  # not what to_dict writes: it would not round-trip
    with pytest.raises(ValueError, match="round-trip"):
        Recipe.from_dict(document)


# ---------------------------------------------------------------------------
# O8 (decided 2026-10-07): a new recipe evaluates in FP32; a document without the key is still FP16
# ---------------------------------------------------------------------------

FP32_EVIDENCE_RECIPE_HASH = "efc1ff67c1bfa8c243ba93ce4a46dfcea74e5afc4b2daffa50498510d53dbc86"   # the recipe_hash of the FP32 benchmark runs of G6


def make_recipe_with_default_precision():
    values = dict(
        model_id="Qwen/Qwen2.5-0.5B-Instruct", model_revision=REVISION, tokenizer_revision=REVISION,
        dtype="torch.float16", schema_hash=SCHEMA, engine_version=ENGINE_VERSION, chunk_elements=262144,
        noise_fingerprint=EXPECTED_NOISE_FINGERPRINT, sigma=0.001, reward_eta=1e-9, workload_hash=WORKLOAD,
        generation_config_sha256=generation_config_sha256(GENERATION_CONFIG),
    )
    return Recipe(**values)                                         # no eval_dtype: the default


def test_a_recipe_that_does_not_say_the_precision_evaluates_in_fp32():
    recipe = make_recipe_with_default_precision()
    assert recipe.eval_dtype == "float32"
    assert recipe.to_dict()["workload"]["eval_dtype"] == "float32"


def test_the_default_recipe_has_the_hash_of_the_fp32_runs_of_g6_and_the_fp16_hash_is_untouched():
    assert make_recipe_with_default_precision().hash == FP32_EVIDENCE_RECIPE_HASH      # evidence of the real runs, not made by this code
    assert make_recipe(eval_dtype="float16").hash == PINNED_RECIPE_HASH


def test_a_document_without_the_key_is_read_as_fp16_whatever_the_default_is():
    document = make_recipe(eval_dtype="float16").to_dict()
    assert "eval_dtype" not in document["workload"]
    recipe = Recipe.from_dict(document)
    assert recipe.eval_dtype == "float16" and recipe.hash == PINNED_RECIPE_HASH


# ---------------------------------------------------------------------------
# G7: the CUDA noise engine and a named workload are choices of the recipe (the CPU engine and the 16-prompt workload leave the document as it was)
# ---------------------------------------------------------------------------

from heteroes.noise.contracts import CUDA_CALL_ELEMENTS, CUDA_ENGINE_VERSION, EXPECTED_CUDA_NOISE_FINGERPRINT  # noqa: E402


def make_cuda_recipe(**changes):
    values = dict(engine_version=CUDA_ENGINE_VERSION, chunk_elements=CUDA_CALL_ELEMENTS, noise_fingerprint=EXPECTED_CUDA_NOISE_FINGERPRINT)
    values.update(changes)
    return make_recipe(**values)


def test_a_cuda_engine_recipe_is_another_recipe_that_says_so_in_the_noise_part_of_the_document():
    recipe = make_cuda_recipe()
    noise = recipe.to_dict()["noise"]
    assert noise == {"engine_version": CUDA_ENGINE_VERSION, "chunk_elements": CUDA_CALL_ELEMENTS, "fingerprint": EXPECTED_CUDA_NOISE_FINGERPRINT}
    assert recipe.hash != PINNED_RECIPE_HASH and recipe.hash != make_cuda_recipe(sigma=0.002).hash


def test_a_cuda_engine_recipe_round_trips_through_json():
    recipe = make_cuda_recipe(eval_dtype="float32")
    again = Recipe.from_dict(json.loads(json.dumps(recipe.to_dict())))
    assert again == recipe and again.hash == recipe.hash and again.engine_version == CUDA_ENGINE_VERSION


@pytest.mark.parametrize("changes", [dict(chunk_elements=262144), dict(chunk_elements=CUDA_CALL_ELEMENTS + 1), dict(noise_fingerprint="1" * 64)])
def test_a_cuda_engine_recipe_must_carry_the_call_size_and_the_fingerprint_of_the_engine(changes):
    with pytest.raises(ValueError):
        make_cuda_recipe(**changes)


def test_the_cpu_engine_recipe_is_untouched_by_the_second_engine():
    assert make_recipe(eval_dtype="float16").hash == PINNED_RECIPE_HASH


def test_the_16_prompt_workload_is_not_named_in_the_document_and_keeps_the_hash():
    assert make_recipe().workload_name == "arith16"
    assert "name" not in make_recipe().to_dict()["workload"]
    assert make_recipe(eval_dtype="float16", workload_name="arith16").hash == PINNED_RECIPE_HASH


def test_another_workload_is_named_in_the_document_and_makes_another_recipe():
    recipe = make_recipe(workload_name="cot_l3_q32")
    assert recipe.to_dict()["workload"]["name"] == "cot_l3_q32"
    assert recipe.hash != make_recipe().hash
    assert Recipe.from_dict(json.loads(json.dumps(recipe.to_dict()))) == recipe


@pytest.mark.parametrize("bad", ["", "cot", None, 3, "ARITH16"])
def test_an_unknown_workload_name_is_refused(bad):
    with pytest.raises((ValueError, TypeError)):
        make_recipe(workload_name=bad)


def test_a_document_that_names_the_default_workload_is_refused_because_the_default_is_written_by_leaving_it_out():
    document = make_recipe().to_dict()
    document["workload"]["name"] = "arith16"
    with pytest.raises(ValueError, match="round-trip"):
        Recipe.from_dict(document)
