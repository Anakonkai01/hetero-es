"""Recipe v2 binds data, file identities, decoding and deterministic generation inputs."""

from dataclasses import dataclass, replace
import math
import numpy as np
from heteroes.manifest import Recipe
from .data import batch, sha
from .models import validate


@dataclass(frozen=True)
class RecipeV2:
    base: Recipe
    model_manifest: dict
    dataset_identity: dict
    batch_size: int
    batch_seed: int
    schedule: dict
    evaluation: dict

    def __post_init__(self):
        validate(self.model_manifest)
        if (
            self.model_manifest["modelId"] != self.base.model_id
            or self.model_manifest["revision"] != self.base.model_revision
            or self.model_manifest["tokenizerRevision"] != self.base.tokenizer_revision
        ):
            raise ValueError("Model recipe identity mismatch")
        if set(self.dataset_identity) != {"contentHash", "splitHashes"} or set(
            self.dataset_identity["splitHashes"]
        ) != {"train", "validation", "test"}:
            raise ValueError("Invalid dataset identity")
        import re

        if any(
            not isinstance(h, str) or not re.fullmatch("[a-f0-9]{64}", h)
            for h in [self.dataset_identity["contentHash"], *self.dataset_identity["splitHashes"].values()]
        ):
            raise ValueError("Invalid dataset hash")
        if (
            type(self.batch_size) is not int
            or self.batch_size < 1
            or type(self.batch_seed) is not int
            or not 0 <= self.batch_seed < 2**53
        ):
            raise ValueError("Invalid batch sampling")
        if set(self.schedule) != {"kind", "initial", "minimum", "generations"} or self.schedule["kind"] not in (
            "constant",
            "cosine",
        ):
            raise ValueError("Invalid sigma schedule")
        if type(self.schedule["generations"]) is not int or self.schedule["generations"] < 1:
            raise ValueError("Invalid generation count")
        if any(
            isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) or v <= 0
            for v in [self.schedule["initial"], self.schedule["minimum"]]
        ):
            raise ValueError("Sigma must remain positive and finite")
        if self.schedule["minimum"] > self.schedule["initial"] or self.schedule["initial"] != self.base.sigma:
            raise ValueError("Sigma schedule initial/minimum mismatch")
        if (
            set(self.evaluation) != {"systemPrompt", "maxNewTokens", "decoder", "extractor"}
            or self.evaluation["decoder"] != "hf_generate"
            or self.evaluation["extractor"] != "answer-line-last-number-v1"
        ):
            raise ValueError("Unsupported v2 evaluation")
        if (
            not isinstance(self.evaluation["systemPrompt"], str)
            or not self.evaluation["systemPrompt"]
            or len(self.evaluation["systemPrompt"]) > 4000
            or type(self.evaluation["maxNewTokens"]) is not int
            or not 1 <= self.evaluation["maxNewTokens"] <= 2048
        ):
            raise ValueError("Invalid prompt/decoder limits")
        if self.base.eval_dtype != "float32":
            raise ValueError("Recipe v2 requires FP32 evaluation")

    def __getattr__(self, name):
        return getattr(self.base, name)

    def to_dict(self):
        return {
            "manifest_version": 2,
            "numerical": self.base.to_dict(),
            "modelFiles": self.model_manifest,
            "dataset": self.dataset_identity,
            "batch": {"size": self.batch_size, "seed": self.batch_seed, "sampler": "sha256-python-random-sample-v1"},
            "sigmaSchedule": self.schedule,
            "evaluation": self.evaluation,
        }

    @property
    def hash(self):
        return sha(self.to_dict())

    @classmethod
    def from_dict(cls, value):
        if (
            set(value)
            != {"manifest_version", "numerical", "modelFiles", "dataset", "batch", "sigmaSchedule", "evaluation"}
            or value["manifest_version"] != 2
        ):
            raise ValueError("Unknown recipe version or keys")
        if (
            set(value["batch"]) != {"size", "seed", "sampler"}
            or value["batch"]["sampler"] != "sha256-python-random-sample-v1"
        ):
            raise ValueError("Unknown sampler")
        recipe = cls(
            Recipe.from_dict(value["numerical"]),
            value["modelFiles"],
            value["dataset"],
            value["batch"]["size"],
            value["batch"]["seed"],
            value["sigmaSchedule"],
            value["evaluation"],
        )
        if recipe.to_dict() != value:
            raise ValueError("Recipe v2 round-trip mismatch")
        return recipe

    def sigma_at(self, generation):
        total = self.schedule["generations"]
        if type(generation) is not int or not 0 <= generation < total:
            raise ValueError("Generation outside schedule")
        initial, minimum = self.schedule["initial"], self.schedule["minimum"]
        sigma = (
            initial
            if self.schedule["kind"] == "constant" or total == 1
            else minimum + (initial - minimum) * (1 + math.cos(math.pi * generation / (total - 1))) / 2
        )
        effective = float(np.float32(sigma))
        if not math.isfinite(effective) or effective <= 0:
            raise ValueError("Effective FP32 sigma is invalid")
        return effective

    def context(self, data, generation):
        if {k: data[k] for k in ("contentHash", "splitHashes")} != self.dataset_identity:
            raise ValueError("Dataset differs from recipe")
        selected = batch(data, generation, self.batch_size, self.batch_seed)
        body = {
            "generation": generation,
            "recipeHash": self.hash,
            "sigmaFloat32": self.sigma_at(generation),
            "batchHash": selected["hash"],
            "batchIndices": selected["indices"],
        }
        return {**body, "contextHash": sha(body)}


def build(loaded, manifest, data, *, sigma, minimum, generations, schedule, batch_size, batch_seed, max_tokens=512):
    from heteroes.model.loading import build_recipe

    base = replace(build_recipe(loaded, sigma=sigma), workload_hash=data["contentHash"])
    return RecipeV2(
        base,
        manifest,
        {k: data[k] for k in ("contentHash", "splitHashes")},
        batch_size,
        batch_seed,
        {"kind": schedule, "initial": sigma, "minimum": minimum, "generations": generations},
        {
            "systemPrompt": "Solve the problem step by step. End your reply with a line 'Answer: <number>'.",
            "maxNewTokens": max_tokens,
            "decoder": "hf_generate",
            "extractor": "answer-line-last-number-v1",
        },
    )
