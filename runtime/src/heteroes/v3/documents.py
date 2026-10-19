"""
Recipe v3 and plan documents (ADR-008 sections 1-3), and the read-only translation of Recipe v1/v2 documents into them.

The recipe is what every worker must agree on; the plan is the coordinator's (population, alpha, coefficient rule, scorer).
Every field is written out: no value means "the default" by being absent. Hashes use the one canonical JSON of
`heteroes.canonical`. A translated v1 document has `model.files` null (v1 pinned the model by revision only); a document
for a new run must pin its files, so only `validate_recipe(..., translated=True)` accepts null.
"""

import math
import re

import numpy as np

from heteroes.canonical import canonical_json_hash
from heteroes.catalog import DECODE_ENGINES, WORKLOAD_NAMES
from heteroes.manifest import EVAL_DTYPES, KNOWN_ENGINES, Recipe
from heteroes.v3.scoring import validate_spec

FORMAT_VERSION = 3
PLAN_VERSION = 1
SAMPLER = "sha256-python-random-sample-v1"
COEFFICIENT_RULES = {"zscore": {1}}

_HEX40, _HEX64 = re.compile("[0-9a-f]{40}"), re.compile("[0-9a-f]{64}")
_RECIPE_KEYS = {"formatVersion", "model", "weightSpace", "schemaHash", "noise", "perturbation", "evaluation", "data"}


def _keys(where, value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(f"{where}: expected exactly the keys {sorted(expected)}")


def _hex(where, value, pattern):
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ValueError(f"{where} has the wrong format")


def _positive(where, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{where} must be a finite positive number")


def _count(where, value, low=1, high=None):
    if type(value) is not int or value < low or (high is not None and value > high):
        raise ValueError(f"{where} out of range")


def _check_weight_space(space):
    kind = space.get("kind") if isinstance(space, dict) else None
    if kind == "full":
        _keys("weightSpace", space, {"kind"})
    elif kind == "subset":
        _keys("weightSpace", space, {"kind", "include"})
        if not isinstance(space["include"], list) or not space["include"]:
            raise ValueError("a subset names at least one pattern")
        for pattern in space["include"]:
            if not isinstance(pattern, str) or not pattern:
                raise ValueError("a subset pattern is a nonempty string")
            try:
                re.compile(pattern)
            except re.error as error:
                raise ValueError(f"invalid subset pattern: {error}") from None
    elif kind == "lora":
        _keys("weightSpace", space, {"kind", "rank", "alpha", "targetModules", "initialAdapterSha256"})
        _count("lora rank", space["rank"], 1, 1024)
        _positive("lora alpha", space["alpha"])
        if not isinstance(space["targetModules"], list) or not space["targetModules"]:
            raise ValueError("LoRA names its target modules")
        if not all(isinstance(m, str) and m for m in space["targetModules"]):
            raise ValueError("a target module is a nonempty name")
        _hex("initialAdapterSha256", space["initialAdapterSha256"], _HEX64)
    else:
        raise ValueError(f"unknown weight space {kind!r}")


def _check_sigma(sigma):
    _keys("perturbation.sigma", sigma, {"kind", "initial", "minimum", "generations"})
    if sigma["kind"] not in ("constant", "cosine"):
        raise ValueError("sigma schedule is constant or cosine")
    _positive("sigma.initial", sigma["initial"])
    _positive("sigma.minimum", sigma["minimum"])
    if sigma["minimum"] > sigma["initial"]:
        raise ValueError("sigma.minimum exceeds sigma.initial")
    if sigma["generations"] is None:
        if sigma["kind"] != "constant":
            raise ValueError("a cosine schedule needs its number of generations")
    else:
        _count("sigma.generations", sigma["generations"])


def validate_recipe(doc, *, translated=False):
    """Check a Recipe v3 document; returns it. `translated` admits a v1 translation (model files not pinned)."""
    _keys("recipe", doc, _RECIPE_KEYS)
    if doc["formatVersion"] != FORMAT_VERSION:
        raise ValueError(f"unknown recipe format {doc['formatVersion']!r}")
    model = doc["model"]
    _keys("model", model, {"id", "revision", "tokenizerRevision", "dtype", "files"})
    if not isinstance(model["id"], str) or not model["id"]:
        raise ValueError("model.id is a nonempty name")
    _hex("model.revision", model["revision"], _HEX40)
    _hex("model.tokenizerRevision", model["tokenizerRevision"], _HEX40)
    if model["dtype"] != "torch.float16":
        raise ValueError("the trainable weights are FP16")
    if model["files"] is None:
        if not translated:
            raise ValueError("a new run pins its model files")
    elif (
        not isinstance(model["files"], dict)
        or not model["files"]
        or not all(
            isinstance(name, str) and name and isinstance(digest, str) and _HEX64.fullmatch(digest)
            for name, digest in model["files"].items()
        )
    ):
        raise ValueError("model.files maps file names to SHA-256 digests")
    _check_weight_space(doc["weightSpace"])
    _hex("schemaHash", doc["schemaHash"], _HEX64)
    noise = doc["noise"]
    _keys("noise", noise, {"engine", "chunkElements", "fingerprint"})
    if noise["engine"] not in KNOWN_ENGINES:
        raise ValueError(f"unknown noise engine {noise['engine']!r}")
    _count("noise.chunkElements", noise["chunkElements"])
    _hex("noise.fingerprint", noise["fingerprint"], _HEX64)
    perturbation = doc["perturbation"]
    _keys("perturbation", perturbation, {"sigma", "antithetic"})
    _check_sigma(perturbation["sigma"])
    if type(perturbation["antithetic"]) is not bool:
        raise ValueError("perturbation.antithetic is true or false")
    evaluation, data = doc["evaluation"], doc["data"]
    _keys("evaluation", evaluation, {"evalDtype", "decoder", "generationConfigSha256", "maxNewTokens", "systemPrompt"})
    if evaluation["evalDtype"] not in EVAL_DTYPES or evaluation["decoder"] not in DECODE_ENGINES:
        raise ValueError("unknown evaluation precision or decoder")
    _hex("evaluation.generationConfigSha256", evaluation["generationConfigSha256"], _HEX64)
    if not isinstance(data, dict) or data.get("kind") not in ("builtin", "dataset"):
        raise ValueError("data is a builtin workload or an imported dataset")
    if data["kind"] == "builtin":
        _keys("data", data, {"kind", "name", "hash"})
        if data["name"] not in WORKLOAD_NAMES:
            raise ValueError(f"unknown builtin workload {data['name']!r}")
        _hex("data.hash", data["hash"], _HEX64)
        # a builtin workload defines its own prompt and token budget (they are part of its hash)
        if evaluation["maxNewTokens"] is not None or evaluation["systemPrompt"] is not None:
            raise ValueError("a builtin workload brings its own prompt and token budget")
    else:
        _keys("data", data, {"kind", "contentHash", "splitHashes", "batch"})
        _hex("data.contentHash", data["contentHash"], _HEX64)
        _keys("data.splitHashes", data["splitHashes"], {"train", "validation", "test"})
        for name, digest in data["splitHashes"].items():
            _hex(f"data.splitHashes.{name}", digest, _HEX64)
        _keys("data.batch", data["batch"], {"size", "seed", "sampler"})
        _count("data.batch.size", data["batch"]["size"])
        _count("data.batch.seed", data["batch"]["seed"], 0, 2**53 - 1)
        if data["batch"]["sampler"] != SAMPLER:
            raise ValueError("unknown batch sampler")
        _count("evaluation.maxNewTokens", evaluation["maxNewTokens"], 1, 2048)
        prompt = evaluation["systemPrompt"]
        if prompt is not None and (not isinstance(prompt, str) or not prompt or len(prompt) > 4000):
            raise ValueError("evaluation.systemPrompt is null or a text of at most 4000 characters")
    return doc


def recipe_hash(doc, *, translated=False):
    return canonical_json_hash(validate_recipe(doc, translated=translated))


def sigma_at(doc, generation):
    """The FP32 sigma of a generation: the rule of Recipe v2 (`study/recipe.py`), constant when no schedule length is known."""
    sigma = doc["perturbation"]["sigma"]
    total = sigma["generations"]
    if type(generation) is not int or generation < 0 or (total is not None and generation >= total):
        raise ValueError("generation outside the schedule")
    initial, minimum = sigma["initial"], sigma["minimum"]
    value = (
        initial
        if sigma["kind"] == "constant" or total == 1
        else minimum + (initial - minimum) * (1 + math.cos(math.pi * generation / (total - 1))) / 2
    )
    effective = float(np.float32(value))
    if not math.isfinite(effective) or effective <= 0:
        raise ValueError("effective FP32 sigma is invalid")
    return effective


def validate_plan(plan, recipe, *, allow_python=False):
    """Check a plan against its (already valid) recipe."""
    _keys(
        "plan", plan, {"formatVersion", "recipeHash", "population", "generations", "alpha", "coefficientRule", "scorer"}
    )
    if plan["formatVersion"] != PLAN_VERSION:
        raise ValueError(f"unknown plan format {plan['formatVersion']!r}")
    if plan["recipeHash"] != canonical_json_hash(recipe):
        raise ValueError("the plan is for another recipe")
    _count("population", plan["population"], 2, 256)
    if recipe["perturbation"]["antithetic"] and plan["population"] % 2:
        raise ValueError("an antithetic population must be even")
    _count("generations", plan["generations"], 1, 1000)
    scheduled = recipe["perturbation"]["sigma"]["generations"]
    if scheduled is not None and scheduled != plan["generations"]:
        raise ValueError("the sigma schedule and the plan disagree on the number of generations")
    _positive("alpha", plan["alpha"])
    rule = plan["coefficientRule"]
    _keys("coefficientRule", rule, {"name", "version", "eta"})
    if rule["version"] not in COEFFICIENT_RULES.get(rule["name"], ()):
        raise ValueError(f"unknown coefficient rule {rule['name']}@{rule['version']}")
    _positive("coefficientRule.eta", rule["eta"])
    validate_spec(plan["scorer"], allow_python=allow_python)
    return plan


def plan_hash(plan, recipe, *, allow_python=False):
    return canonical_json_hash(validate_plan(plan, recipe, allow_python=allow_python))


def _declarative(name):
    return {"kind": "declarative", "name": name, "version": 1, "codeSha256": None, "config": {}}


def _from_numerical(v1, files):
    recipe = Recipe.from_dict(v1)  # validates the v1 document and its round trip
    doc = {
        "formatVersion": FORMAT_VERSION,
        "model": {
            "id": recipe.model_id,
            "revision": recipe.model_revision,
            "tokenizerRevision": recipe.tokenizer_revision,
            "dtype": recipe.dtype,
            "files": files,
        },
        "weightSpace": {"kind": "full"},
        "schemaHash": recipe.schema_hash,
        "noise": {
            "engine": recipe.engine_version,
            "chunkElements": recipe.chunk_elements,
            "fingerprint": recipe.noise_fingerprint,
        },
        "perturbation": {
            "sigma": {"kind": "constant", "initial": recipe.sigma, "minimum": recipe.sigma, "generations": None},
            "antithetic": False,
        },
        "evaluation": {
            "evalDtype": recipe.eval_dtype,
            "decoder": recipe.decode_engine,
            "generationConfigSha256": recipe.generation_config_sha256,
            "maxNewTokens": None,
            "systemPrompt": None,
        },
        "data": {"kind": "builtin", "name": recipe.workload_name, "hash": recipe.workload_hash},
    }
    return doc, recipe


def from_v1(v1):
    """(recipe v3 document, the plan fields v1 fixed: coefficient rule and scorer) of a Recipe v1 document."""
    doc, recipe = _from_numerical(v1, None)
    scorer = "last-integer" if recipe.workload_name == "arith16" else "answer-line-integer"
    fixed = {
        "coefficientRule": {"name": "zscore", "version": 1, "eta": recipe.reward_eta},
        "scorer": _declarative(scorer),
    }
    validate_recipe(doc, translated=True)
    return doc, fixed


def from_v2(v2):
    """(recipe v3 document, the plan fields v2 fixed) of a Recipe v2 document (`study/recipe.py` to_dict)."""
    from heteroes.study.recipe import RecipeV2

    v2_recipe = RecipeV2.from_dict(v2)  # validates and round-trips
    doc, base = _from_numerical(v2["numerical"], dict(v2["modelFiles"]["files"]))
    schedule = v2_recipe.schedule
    doc["perturbation"]["sigma"] = {
        "kind": schedule["kind"],
        "initial": schedule["initial"],
        "minimum": schedule["minimum"],
        "generations": schedule["generations"],
    }
    doc["evaluation"]["maxNewTokens"] = v2_recipe.evaluation["maxNewTokens"]
    doc["evaluation"]["systemPrompt"] = v2_recipe.evaluation["systemPrompt"]
    doc["evaluation"]["decoder"] = v2_recipe.evaluation["decoder"]
    doc["data"] = {
        "kind": "dataset",
        "contentHash": v2_recipe.dataset_identity["contentHash"],
        "splitHashes": dict(v2_recipe.dataset_identity["splitHashes"]),
        "batch": {"size": v2_recipe.batch_size, "seed": v2_recipe.batch_seed, "sampler": SAMPLER},
    }
    fixed = {
        "coefficientRule": {"name": "zscore", "version": 1, "eta": base.reward_eta},
        "scorer": _declarative("answer-line-last-number"),
    }
    validate_recipe(doc)
    return doc, fixed
