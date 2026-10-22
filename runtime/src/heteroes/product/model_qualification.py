"""Lab-owned references for newly registered models; trusted full-model probes, never researcher code or adapters.

Only the first device establishes a reference. Other devices reproduce its pinned recipe, both signs twice, texts,
rewards and exact restoration. Validation and comparison are CPU-safe so the lab can independently check reports.
This probes the chosen short workload; it is not a promise that every greedy decode agrees across hardware.
"""

import math
import re

from heteroes.canonical import canonical_json_hash
from heteroes.noise.contracts import ENGINE_VERSION, CPU_NOISE_FINGERPRINTS
from heteroes.product.qualification_v3 import SEED, cell_configs, observe, reference_rows, verify
from heteroes.study.models import validate as validate_manifest
from heteroes.v3 import data

PROFILE = "model-v3@1"
# Pinned protocol fact (not a new engine): checked against noise.selftest by the runtime tests. The CPU lab ships no
# NumPy, so validating a reference must not import the numerical runtime or regenerate noise.
NOISE_FINGERPRINT = "b94575345e870b1606cb4d6a0c4aa49b054cfbfc50571d809653d01bce9184d3"
REFERENCE_KEYS = {"formatVersion", "profile", "manifestHash", "seed", "rows", "cell"}
OBSERVATION_KEYS = {
    "recipeHash",
    "modelManifestHash",
    "parentSha256",
    "restoredSha256",
    "outputsHash",
    "reward",
    "perturbedSha256",
}


def _documents(manifest, schema_hash, generation_config_hash, engine=ENGINE_VERSION):
    if engine not in CPU_NOISE_FINGERPRINTS:
        raise ValueError("Unknown CPU noise engine")
    for digest in (schema_hash, generation_config_hash):
        if not isinstance(digest, str) or re.fullmatch("[a-f0-9]{64}", digest) is None:
            raise ValueError("Invalid reference schema or generation configuration hash")
    dataset = data.build(reference_rows(), split_seed=42)
    recipe = {
        "formatVersion": 3,
        "model": {
            "id": manifest["modelId"],
            "revision": manifest["revision"],
            "tokenizerRevision": manifest["tokenizerRevision"],
            "dtype": "torch.float16",
            "files": manifest["files"],
        },
        "weightSpace": {"kind": "full"},
        "schemaHash": schema_hash,
        "noise": {
            "engine": engine,
            "chunkElements": 262144,
            "fingerprint": CPU_NOISE_FINGERPRINTS[engine],
        },
        "perturbation": {
            "sigma": {"kind": "constant", "initial": 0.001, "minimum": 0.001, "generations": 1},
            "antithetic": True,
        },
        "evaluation": {
            "evalDtype": "float32",
            "decoder": "hf_generate",
            "generationConfigSha256": generation_config_hash,
            "maxNewTokens": 32,
            "systemPrompt": None,
        },
        "data": {
            "kind": "dataset",
            "contentHash": dataset["contentHash"],
            "splitHashes": dataset["splitHashes"],
            "batch": {"size": 4, "seed": 11, "sampler": data.SAMPLER},
        },
    }
    plan = {
        "formatVersion": 1,
        "recipeHash": canonical_json_hash(recipe),
        "population": 2,
        "generations": 1,
        "alpha": 0.001,
        "coefficientRule": {"name": "zscore", "version": 1, "eta": 1e-9},
        "scorer": {"kind": "declarative", "name": "last-integer", "version": 1, "codeSha256": None, "config": {}},
    }
    return recipe, plan


def _check_observation(value, recipe_hash, manifest_hash):
    if not isinstance(value, dict) or set(value) != OBSERVATION_KEYS:
        raise ValueError("Model qualification observation fields differ")
    for key in OBSERVATION_KEYS - {"reward"}:
        if not isinstance(value[key], str) or re.fullmatch("[a-f0-9]{64}", value[key]) is None:
            raise ValueError("Model qualification digest is invalid")
    if type(value["reward"]) not in (int, float) or not math.isfinite(value["reward"]):
        raise ValueError("Model qualification reward must be finite")
    if (
        value["recipeHash"] != recipe_hash
        or value["modelManifestHash"] != manifest_hash
        or value["parentSha256"] != value["restoredSha256"]
        or value["parentSha256"] == value["perturbedSha256"]
    ):
        raise ValueError("Model qualification identity, perturbation or exact restore differs")


def check_reference(reference, manifest):
    """Validate every executable input before loading any model; the lab applies the same check to a first report."""
    validate_manifest(manifest, allow_any=True)
    if (
        not isinstance(reference, dict)
        or set(reference) != REFERENCE_KEYS
        or type(reference["formatVersion"]) is not int
        or reference["formatVersion"] != 1
        or reference["profile"] != PROFILE
        or reference["manifestHash"] != canonical_json_hash(manifest)
        or type(reference["seed"]) is not int
        or reference["seed"] != SEED
        or reference["rows"] != reference_rows()
    ):
        raise ValueError("Invalid pinned model qualification reference")
    cell = reference["cell"]
    if not isinstance(cell, dict) or set(cell) != {"config", "recipe", "plan", "expected", "negativeExpected"}:
        raise ValueError("Invalid model qualification cell")
    engine = cell.get("recipe", {}).get("noise", {}).get("engine")
    if engine not in CPU_NOISE_FINGERPRINTS:
        raise ValueError("Unknown CPU noise engine")
    config = cell_configs(manifest["modelId"], manifest["revision"], None if engine == ENGINE_VERSION else engine)[
        "full"
    ]
    if canonical_json_hash(cell["config"]) != canonical_json_hash(config):
        raise ValueError("Model qualification uses the trusted full-model probe only")
    try:
        recipe, plan = _documents(
            manifest, cell["recipe"]["schemaHash"], cell["recipe"]["evaluation"]["generationConfigSha256"], engine
        )
    except (KeyError, TypeError):
        raise ValueError("Invalid model qualification recipe") from None
    if canonical_json_hash(cell["recipe"]) != canonical_json_hash(recipe) or canonical_json_hash(
        cell["plan"]
    ) != canonical_json_hash(plan):
        raise ValueError("Model qualification recipe or plan differs from trusted inputs")
    recipe_hash = canonical_json_hash(recipe)
    for name in ("expected", "negativeExpected"):
        _check_observation(cell[name], recipe_hash, reference["manifestHash"])
    if (
        cell["expected"]["parentSha256"] != cell["negativeExpected"]["parentSha256"]
        or cell["expected"]["perturbedSha256"] == cell["negativeExpected"]["perturbedSha256"]
    ):
        raise ValueError("Model qualification signs must perturb the same parent differently")
    return reference


def verify_observations(reference, observations):
    """Compare JSON reports independently on the lab, including both repeats and JSON value types."""
    if not isinstance(observations, dict) or set(observations) != {"1", "-1"}:
        raise ValueError("Model qualification needs both signed observations")
    cell = reference["cell"]
    for sign, name in (("1", "expected"), ("-1", "negativeExpected")):
        repeated = observations[sign]
        if not isinstance(repeated, list) or len(repeated) != 2:
            raise ValueError("Model qualification needs two repeats of each sign")
        for actual in repeated:
            _check_observation(actual, cell["expected"]["recipeHash"], reference["manifestHash"])
            if canonical_json_hash(actual) != canonical_json_hash(cell[name]):
                raise ValueError("Model qualification differs from the lab reference")
    return verify(cell, {sign: observations[str(sign)] for sign in (1, -1)})


def build_reference(model_path, manifest, device="cuda", emit=lambda event: None, *, engine=ENGINE_VERSION):
    validate_manifest(manifest, allow_any=True)
    config = cell_configs(manifest["modelId"], manifest["revision"], None if engine == ENGINE_VERSION else engine)[
        "full"
    ]
    run, observed = observe(model_path, {**config, "noiseEngineVersion": engine}, reference_rows(), SEED, device, emit)
    observations = {str(sign): rows for sign, rows in observed.items()}
    reference = {
        "formatVersion": 1,
        "profile": PROFILE,
        "manifestHash": canonical_json_hash(manifest),
        "seed": SEED,
        "rows": reference_rows(),
        "cell": {
            "config": config,
            "recipe": run.recipe,
            "plan": run.plan,
            "expected": observations["1"][0],
            "negativeExpected": observations["-1"][0],
        },
    }
    check_reference(reference, manifest)
    verify_observations(reference, observations)
    return reference, observations


def qualify(model_path, manifest, reference, device="cuda", emit=lambda event: None):
    check_reference(reference, manifest)
    cell = reference["cell"]
    _, observed = observe(model_path, cell["config"], reference["rows"], reference["seed"], device, emit, expected=cell)
    observations = {str(sign): rows for sign, rows in observed.items()}
    verify_observations(reference, observations)
    return observations
