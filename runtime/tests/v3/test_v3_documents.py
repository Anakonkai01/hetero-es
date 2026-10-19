"""
Recipe v3 and plan documents (ADR-008 sections 1-3) and the read-only translation of the recorded v1 recipes and of a v2
recipe. Translation must keep every numerical field: model, schema, noise, sigma, evaluation precision and decoder.
"""

import copy
import json
from pathlib import Path

import numpy as np
import pytest

from heteroes.canonical import canonical_json_hash
from heteroes.manifest import Recipe
from heteroes.noise.contracts import DEFAULT_CHUNK_ELEMENTS, ENGINE_VERSION
from heteroes.noise.selftest import EXPECTED_NOISE_FINGERPRINT
from heteroes.study.data import dataset
from heteroes.study.recipe import RecipeV2
from heteroes.v3.documents import from_v1, from_v2, plan_hash, recipe_hash, sigma_at, validate_plan, validate_recipe

GOLDEN = json.loads((Path(__file__).parents[1] / "fixtures/golden-identities.json").read_text(encoding="utf-8"))
REVISION = "7ae557604adf67be50417f59c2c2f167def9a775"
# The v3 hashes of the eight recorded v1 recipes, frozen on 2026-10-19: the mapping table of ADR-008 section 9 must not drift.
FROZEN_TRANSLATION = "cae5f3793bebcd49bdf1bdaeacaef20b973aaf48e94e2dbaad3ebf4d79f4d1f0"


def v2_recipe(kind="cosine", generations=5):
    data = dataset(
        {"all": {"format": "json", "content": json.dumps([{"prompt": f"Q{i}", "answer": i} for i in range(20)])}}
    )
    base = Recipe(
        "Qwen/Qwen2.5-0.5B-Instruct", REVISION, REVISION, "torch.float16", "a" * 64, ENGINE_VERSION,
        DEFAULT_CHUNK_ELEMENTS, EXPECTED_NOISE_FINGERPRINT, 0.001, 1e-9, data["contentHash"], "b" * 64,
    )  # fmt: skip
    manifest = {
        "formatVersion": 1, "modelId": base.model_id, "revision": REVISION, "tokenizerRevision": REVISION,
        "format": "safetensors", "files": {"config.json": "c" * 64, "model.safetensors": "d" * 64, "tokenizer.json": "e" * 64},
    }  # fmt: skip
    evaluation = {
        "systemPrompt": "Solve.",
        "maxNewTokens": 64,
        "decoder": "hf_generate",
        "extractor": "answer-line-last-number-v1",
    }
    return RecipeV2(
        base, manifest, {k: data[k] for k in ("contentHash", "splitHashes")}, 8, 11,
        {"kind": kind, "initial": 0.001, "minimum": 0.00025, "generations": generations}, evaluation,
    )  # fmt: skip


def plan_for(recipe, **changes):
    plan = {
        "formatVersion": 1,
        "recipeHash": canonical_json_hash(recipe),
        "population": 8,
        "generations": 5,
        "alpha": 0.001,
        "coefficientRule": {"name": "zscore", "version": 1, "eta": 1e-9},
        "scorer": {
            "kind": "declarative",
            "name": "answer-line-last-number",
            "version": 1,
            "codeSha256": None,
            "config": {},
        },
    }
    return {**plan, **changes}


def test_every_recorded_v1_recipe_translates_with_its_numerics():
    assert len(GOLDEN["recipes"]) == 8
    for entry in GOLDEN["recipes"]:
        v1 = Recipe.from_dict(entry["recipe"])
        doc, fixed = from_v1(entry["recipe"])
        assert doc["model"] == {"id": v1.model_id, "revision": v1.model_revision, "tokenizerRevision": v1.tokenizer_revision, "dtype": v1.dtype, "files": None}  # fmt: skip
        assert doc["schemaHash"] == v1.schema_hash and doc["weightSpace"] == {"kind": "full"}
        assert doc["noise"] == {"engine": v1.engine_version, "chunkElements": v1.chunk_elements, "fingerprint": v1.noise_fingerprint}  # fmt: skip
        assert sigma_at(doc, 0) == sigma_at(doc, 999) == float(np.float32(v1.sigma))
        assert (doc["evaluation"]["evalDtype"], doc["evaluation"]["decoder"]) == (v1.eval_dtype, v1.decode_engine)
        assert doc["data"] == {"kind": "builtin", "name": v1.workload_name, "hash": v1.workload_hash}
        assert fixed["coefficientRule"] == {"name": "zscore", "version": 1, "eta": v1.reward_eta}
        assert fixed["scorer"]["name"] == ("last-integer" if v1.workload_name == "arith16" else "answer-line-integer")
        assert recipe_hash(doc, translated=True) != entry["recorded_hashes"][0]  # a new identity, mapped, not reused
        with pytest.raises(ValueError, match="pins its model files"):
            validate_recipe(doc)


def test_the_translation_of_recorded_recipes_is_frozen():
    hashes = sorted(recipe_hash(from_v1(entry["recipe"])[0], translated=True) for entry in GOLDEN["recipes"])
    assert len(set(hashes)) == 8
    assert canonical_json_hash(hashes) == FROZEN_TRANSLATION


def test_a_v2_recipe_translates_with_its_schedule_data_and_prompt():
    for kind in ("constant", "cosine"):
        v2 = v2_recipe(kind)
        doc, fixed = from_v2(v2.to_dict())
        assert all(sigma_at(doc, g) == v2.sigma_at(g) for g in range(5))
        with pytest.raises(ValueError):
            sigma_at(doc, 5)
        assert doc["model"]["files"] == v2.model_manifest["files"]
        assert doc["data"]["contentHash"] == v2.dataset_identity["contentHash"]
        assert doc["data"]["batch"] == {"size": 8, "seed": 11, "sampler": "sha256-python-random-sample-v1"}
        assert (doc["evaluation"]["systemPrompt"], doc["evaluation"]["maxNewTokens"]) == ("Solve.", 64)
        assert fixed["scorer"]["name"] == "answer-line-last-number"
        assert recipe_hash(doc)


def test_recipes_are_strict():
    doc, _ = from_v2(v2_recipe().to_dict())
    cases = []
    for path, value in [
        (("extra",), 1),
        (("formatVersion",), 2),
        (("model", "dtype"), "torch.bfloat16"),
        (("model", "files"), {}),
        (("weightSpace",), {"kind": "subset", "include": []}),
        (("weightSpace",), {"kind": "subset", "include": ["("]}),
        (
            ("weightSpace",),
            {"kind": "lora", "rank": 0, "alpha": 16, "targetModules": ["q_proj"], "initialAdapterSha256": "f" * 64},
        ),
        (("weightSpace",), {"kind": "dense"}),
        (("noise", "engine"), "other"),
        (("perturbation", "antithetic"), 1),
        (("perturbation", "sigma", "generations"), None),
        (("perturbation", "sigma", "minimum"), 0.01),
        (("evaluation", "decoder"), "vllm"),
        (("evaluation", "maxNewTokens"), None),
        (("data", "batch", "sampler"), "other"),
    ]:
        changed = copy.deepcopy(doc)
        target = changed
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = value
        cases.append(changed)
    for changed in cases:
        with pytest.raises(ValueError):
            validate_recipe(changed)
    for space in (
        {"kind": "subset", "include": [r"model\.layers\.2[0-3]\."]},
        {
            "kind": "lora",
            "rank": 8,
            "alpha": 16,
            "targetModules": ["q_proj", "v_proj"],
            "initialAdapterSha256": "f" * 64,
        },
    ):
        assert validate_recipe({**doc, "weightSpace": space})
    builtin, _ = from_v1(GOLDEN["recipes"][0]["recipe"])
    builtin["evaluation"]["maxNewTokens"] = 32
    with pytest.raises(ValueError, match="builtin"):
        validate_recipe(builtin, translated=True)


def test_plans_bind_their_recipe_and_refuse_what_cannot_run():
    doc, _ = from_v2(v2_recipe().to_dict())
    assert plan_hash(plan_for(doc), doc)
    antithetic = {**doc, "perturbation": {**doc["perturbation"], "antithetic": True}}
    python = {"kind": "python", "name": "mine", "version": 1, "codeSha256": "a" * 64, "config": {}}
    for plan, recipe in [
        (plan_for(doc, recipeHash="0" * 64), doc),
        (plan_for(antithetic, population=7), antithetic),
        (plan_for(doc, generations=6), doc),
        (plan_for(doc, alpha=0), doc),
        (plan_for(doc, coefficientRule={"name": "adam", "version": 1, "eta": 1e-9}), doc),
        (plan_for(doc, scorer=python), doc),
        ({**plan_for(doc), "extra": 1}, doc),
    ]:
        with pytest.raises(ValueError):
            validate_plan(plan, recipe)
    assert validate_plan(plan_for(doc, scorer=python), doc, allow_python=True)
    assert validate_plan(plan_for(antithetic, population=8), antithetic)
