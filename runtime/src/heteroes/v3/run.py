"""
A Recipe v3 run (ADR-008): the recipe and plan documents as the object the coordinator, executor and worker runtime use,
the documents built from a user's configuration, and the coordinator-side scorer of the run.

A native v3 run reads an imported dataset (`data.kind == "dataset"`); the builtin workloads exist in v3 only as
translations of recorded v1 runs, for replay.
"""

import importlib.util
import sys
from pathlib import Path

from heteroes.canonical import canonical_json_hash
from heteroes.v3 import data as v3data
from heteroes.v3.coefficients import check_rule
from heteroes.v3.documents import alpha_at, coefficient_rule_id, recipe_hash, sigma_at, validate_plan, validate_recipe
from heteroes.v3.scoring import code_sha256, score as score_texts


class RecipeV3Run:
    """What `Coordinator`, `CandidateExecutor` and `WorkerRuntime` read from a recipe, for a v3 recipe and its plan."""

    def __init__(self, recipe: dict, plan: dict, *, allow_python=True):
        validate_recipe(recipe)
        validate_plan(plan, recipe, allow_python=allow_python)
        if recipe["data"]["kind"] != "dataset":
            raise ValueError("a v3 run reads an imported dataset (builtin workloads are replayed, not run)")
        self.recipe, self.plan = recipe, plan
        self.hash = recipe_hash(recipe)
        self.plan_hash = canonical_json_hash(plan)
        noise, evaluation = recipe["noise"], recipe["evaluation"]
        self.engine_version, self.chunk_elements = noise["engine"], noise["chunkElements"]
        self.eval_dtype, self.decode_engine = evaluation["evalDtype"], evaluation["decoder"]
        self.chunk = evaluation.get("chunk")  # None: the executor's default, as for documents written before the key
        # ADR-010: the chunks a worker may evaluate with (one, the recipe's, unless the recipe lists more)
        self.chunks = tuple(evaluation.get("chunks") or ([self.chunk] if self.chunk is not None else []))
        self.sigma = recipe["perturbation"]["sigma"]["initial"]
        self.reward_eta = plan["coefficientRule"]["eta"]
        self.coefficient_rule = coefficient_rule_id(plan["coefficientRule"])
        self.update_rule = plan.get("update")  # None: the plain step; a momentum rule goes into every update record
        self.antithetic = recipe["perturbation"]["antithetic"]
        self.workload_name = None
        # what the generation of texts reads (`study.evaluation.generate_rows`); the answers are scored elsewhere
        self.evaluation = {
            "systemPrompt": evaluation["systemPrompt"],
            "maxNewTokens": evaluation["maxNewTokens"],
            "decoder": evaluation["decoder"],
        }
        if "promptFormat" in evaluation:
            self.evaluation["promptFormat"] = evaluation["promptFormat"]
        # a Python sampler (python@1:<sha>): its function, set on the coordinator only, and the batches it chose
        self.python_sampler = v3data.python_sampler(recipe["data"]["batch"]["sampler"])
        self.sampler_function = None
        self._chosen = {}

    def to_dict(self) -> dict:
        return self.recipe

    def alpha_at(self, generation):
        return alpha_at(self.plan, generation)

    def batch(self, data, generation, indices=None):
        """The rows of a generation. A Python sampler's `indices` come from the coordinator's frozen context; the
        coordinator itself asks its `sampler_function` (once per generation, so the scorer reads the same rows)."""
        if {k: data[k] for k in ("contentHash", "splitHashes")} != {
            k: self.recipe["data"][k] for k in ("contentHash", "splitHashes")
        }:
            raise ValueError("Dataset differs from recipe")
        size, seed = self.recipe["data"]["batch"]["size"], self.recipe["data"]["batch"]["seed"]
        if self.python_sampler and indices is None:
            indices = self._chosen.get(generation)
            if indices is None and self.sampler_function is not None:
                indices = self.sampler_function(generation, size, len(data["splits"]["train"]), seed)
        selected = v3data.batch(data, generation, size, seed, self.recipe["data"]["batch"]["sampler"], indices)
        if self.python_sampler and self.sampler_function is not None:
            self._chosen.setdefault(generation, selected["indices"])
        return selected

    def context(self, data, generation, indices=None):
        """The inputs of a generation, frozen in the ledger before it opens: sigma, batch, scorer and coefficient rule."""
        selected = self.batch(data, generation, indices)
        body = {
            "generation": generation,
            "recipeHash": self.hash,
            "planHash": self.plan_hash,
            "sigmaFloat32": sigma_at(self.recipe, generation),
            "batchHash": selected["hash"],
            "batchIndices": selected["indices"],
            "scorer": self.plan["scorer"],
            "coefficientRule": self.plan["coefficientRule"],
        }
        # keys that only plans with an alpha schedule or momentum have, so that earlier contexts keep their hashes
        if isinstance(self.plan["alpha"], dict):
            body["alphaFloat32"] = self.alpha_at(generation)
        if self.update_rule is not None:
            body["update"] = self.update_rule
        return {**body, "contextHash": canonical_json_hash(body)}


def load_python_scorer(path, function):
    """The scorer function `function` of the file `path`, and the SHA-256 of that file (its identity in the plan)."""
    path = Path(path)
    spec = importlib.util.spec_from_file_location(f"heteroes_scorer_{code_sha256(path)[:12]}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    scorer = getattr(module, function, None)
    if not callable(scorer):
        raise ValueError(f"{path} has no function {function!r}")
    return scorer, code_sha256(path)


def make_scorer(run: RecipeV3Run, data, python_scorer=None):
    """`score(generation, descriptor, completions) -> reward` for the coordinator: the rows of that generation's batch."""
    spec = run.plan["scorer"]
    if spec["kind"] == "python" and python_scorer is None:
        raise ValueError("a Python scorer must be loaded to score")

    def score(generation, descriptor, completions):
        rows = run.batch(data, generation)["rows"]
        return score_texts(spec, completions, rows, python_scorer)[0]

    return score


def build_documents(
    config, *, model_files, revision, schema_hash, generation_config_sha256, dataset, adapter_sha256=None
):
    """
    (recipe, plan) from a user's configuration (see `heteroes.sdk.ESConfig`) and the facts measured on the model and data.
    Everything that is not chosen gets the default here, written out in the documents.
    """
    from heteroes.noise.contracts import CUDA_CALL_ELEMENTS, CUDA_ENGINE_VERSION, DEFAULT_CHUNK_ELEMENTS, ENGINE_VERSION
    from heteroes.noise.contracts import EXPECTED_CUDA_NOISE_FINGERPRINT
    from heteroes.noise.selftest import EXPECTED_NOISE_FINGERPRINT

    engine = config.get("noiseEngine", "cpu")
    noise = {
        "cpu": {
            "engine": ENGINE_VERSION,
            "chunkElements": DEFAULT_CHUNK_ELEMENTS,
            "fingerprint": EXPECTED_NOISE_FINGERPRINT,
        },
        "cuda": {
            "engine": CUDA_ENGINE_VERSION,
            "chunkElements": CUDA_CALL_ELEMENTS,
            "fingerprint": EXPECTED_CUDA_NOISE_FINGERPRINT,
        },
    }[engine]
    space = dict(config.get("weightSpace") or {"kind": "full"})
    if space["kind"] == "lora":
        space = {k: space[k] for k in ("kind", "rank", "alpha", "targetModules")} | {
            "initialAdapterSha256": adapter_sha256
        }
    sigma = config["sigma"]
    generations = config["generations"]
    recipe = {
        "formatVersion": 3,
        "model": {
            "id": config["model"]["id"],
            "revision": revision,
            "tokenizerRevision": revision,
            "dtype": "torch.float16",
            "files": model_files,
        },
        "weightSpace": space,
        "schemaHash": schema_hash,
        "noise": noise,
        "perturbation": {
            "sigma": {
                "kind": sigma.get("kind", "constant"),
                "initial": sigma["initial"],
                "minimum": sigma.get("minimum", sigma["initial"]),
                "generations": generations,
            },
            "antithetic": bool(config.get("antithetic", False)),
        },
        "evaluation": {
            "evalDtype": config.get("evalDtype", "float32"),
            "decoder": config.get("decoder", "hf_generate"),
            "generationConfigSha256": generation_config_sha256,
            "maxNewTokens": config.get("maxNewTokens", 256),
            "systemPrompt": config.get("systemPrompt"),
        }
        | ({"chunk": config["evalChunk"]} if "evalChunk" in config else {})
        | ({"chunks": sorted(set(config["evalChunks"]))} if config.get("evalChunks") else {})
        | ({"promptFormat": config["promptFormat"]} if config.get("promptFormat") is not None else {}),
        "data": {
            "kind": "dataset",
            "contentHash": dataset["contentHash"],
            "splitHashes": dataset["splitHashes"],
            "batch": {
                "size": config["batchSize"],
                "seed": config.get("batchSeed", 11),
                "sampler": config.get("sampler", v3data.SAMPLER),
            },
        },
    }
    validate_recipe(recipe)
    # "zscore@1", "centered-rank@1" or "python@1:<code sha256>" (`heteroes.v3.coefficients`)
    rule = check_rule(config.get("coefficientRule", "zscore@1"))
    eta = config.get("eta", 1e-9)
    if rule.startswith("python@"):
        coefficient_rule = {"name": "python", "version": 1, "eta": eta, "codeSha256": rule.split(":", 1)[1]}
    else:
        name, version = rule.rsplit("@", 1)
        coefficient_rule = {"name": name, "version": int(version), "eta": eta}
    alpha = config["alpha"]
    if config.get("alphaSchedule") is not None:
        schedule = config["alphaSchedule"]
        alpha = {"kind": schedule["kind"], "initial": alpha, "minimum": schedule.get("minimum", alpha)}
    plan = {
        "formatVersion": 1,
        "recipeHash": canonical_json_hash(recipe),
        "population": config["population"],
        "generations": generations,
        "alpha": alpha,
        "coefficientRule": coefficient_rule,
        "scorer": config["scorerSpec"],
    }
    if config.get("momentum") is not None:
        plan["update"] = {
            "kind": "momentum",
            "beta": config["momentum"]["beta"],
            "window": config["momentum"]["window"],
        }
    validate_plan(plan, recipe, allow_python=True)
    return recipe, plan
