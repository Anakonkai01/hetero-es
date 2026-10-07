import hashlib
import math
import re
from dataclasses import dataclass

import numpy as np

from heteroes.canonical import canonical_json_hash
from heteroes.noise.contracts import ENGINE_VERSION

MANIFEST_VERSION = 1
SUPPORTED_DTYPE = "torch.float16"
# The precision in which the forward pass of the EVALUATION runs (the weights, the noise and the update stay FP16 / FP32 as the contract
# says). FP32 is the default of new recipes (decision O8, 2026-10-07, numerical contract section 15). A recipe document WITHOUT the
# key means FP16 (LEGACY_EVAL_DTYPE) and FP16 is still left out of the document, so that the hash of every recipe made before G6 is
# unchanged; FP32 is written in `workload` (that is the same document as in G6, so its hash did not change either).
EVAL_DTYPES = ("float16", "float32")
LEGACY_EVAL_DTYPE = "float16"
DEFAULT_EVAL_DTYPE = "float32"

# Seeds travel as JSON. JavaScript reads integers exactly only below 2**53, so v1 does not allow more.
MAX_SEED = 2**53  # exclusive

# What the update does, as labels. They are part of the recipe hash, so changing the numerics of the update
# (numerical contract, sections 7 and 8) means a new manifest version.
UPDATE_RECIPE = {
    "epsilon": "canonical_fp16_upcast_fp32",
    "accumulation_dtype": "float32",
    "reward_standardization": "population_std_float64_zero_below_eta",
    "candidate_order": "listed_order",
}

_HEX40 = re.compile(r"[0-9a-f]{40}")
_HEX64 = re.compile(r"[0-9a-f]{64}")
_NAME = re.compile(r"[A-Za-z0-9_.-]+")


def _check_text(name: str, value, pattern=None) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string, got {type(value).__name__}")
    if pattern is None:
        if not value:
            raise ValueError(f"{name} must not be empty")
    elif not pattern.fullmatch(value):
        raise ValueError(f"{name} has the wrong format: {value!r}")


def _check_int(name: str, value, minimum: int, maximum: int | None = None) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer, got {type(value).__name__}")
    if value < minimum or (maximum is not None and value >= maximum):
        raise ValueError(f"{name} out of range: {value}")


def _check_positive_finite(name: str, value) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number, got {type(value).__name__}")
    if not (math.isfinite(value) and value > 0):
        raise ValueError(f"{name} must be finite and positive, got {value}")


def _check_keys(what: str, data: dict, expected: set) -> None:
    if set(data) != expected:
        raise ValueError(f"{what}: expected the keys {sorted(expected)}, got {sorted(data)}")


def effective_generation_config(config: dict) -> dict:
    """
    The generation settings that can change an output: the values that are set, without the library version.
    A newer transformers adds keys whose value is None and writes its own version into the dict, so the raw
    dict (and its hash) is not comparable between library versions.
    """
    return {key: value for key, value in config.items() if value is not None and key != "transformers_version"}


def generation_config_sha256(config: dict) -> str:
    return canonical_json_hash(effective_generation_config(config))


@dataclass(frozen=True)
class Recipe:
    """
    Everything that must be the same on every machine for a candidate to be the same candidate.
    The same for all candidates of an experiment; its hash is what two machines compare.

    Deliberately NOT in it: the NumPy, torch and transformers versions (the noise fingerprint and the workload
    check what really matters), and anything operational (worker, attempt, lease, retry, reward, time).
    """
    model_id: str
    model_revision: str
    tokenizer_revision: str
    dtype: str
    schema_hash: str
    engine_version: str
    chunk_elements: int
    noise_fingerprint: str
    sigma: float
    reward_eta: float
    workload_hash: str
    generation_config_sha256: str
    eval_dtype: str = DEFAULT_EVAL_DTYPE

    def __post_init__(self):
        _check_text("model_id", self.model_id)
        _check_text("model_revision", self.model_revision, _HEX40)
        _check_text("tokenizer_revision", self.tokenizer_revision, _HEX40)
        _check_text("dtype", self.dtype)
        if self.dtype != SUPPORTED_DTYPE:
            raise ValueError(f"manifest v1 supports only {SUPPORTED_DTYPE}, got {self.dtype}")
        _check_text("schema_hash", self.schema_hash, _HEX64)
        _check_text("engine_version", self.engine_version)
        if self.engine_version != ENGINE_VERSION:
            raise ValueError(f"manifest v1 knows only the noise engine {ENGINE_VERSION}, got {self.engine_version}")
        _check_int("chunk_elements", self.chunk_elements, 1)
        _check_text("noise_fingerprint", self.noise_fingerprint, _HEX64)
        _check_positive_finite("sigma", self.sigma)
        _check_positive_finite("reward_eta", self.reward_eta)
        _check_text("workload_hash", self.workload_hash, _HEX64)
        _check_text("generation_config_sha256", self.generation_config_sha256, _HEX64)
        _check_text("eval_dtype", self.eval_dtype)
        if self.eval_dtype not in EVAL_DTYPES:
            raise ValueError(f"eval_dtype must be one of {EVAL_DTYPES}, got {self.eval_dtype!r}")

    def to_dict(self) -> dict:
        return {
            "manifest_version": MANIFEST_VERSION,
            "model": {
                "id": self.model_id,
                "revision": self.model_revision,
                "tokenizer_revision": self.tokenizer_revision,
                "dtype": self.dtype,
                "schema_hash": self.schema_hash,
            },
            "noise": {
                "engine_version": self.engine_version,
                "chunk_elements": self.chunk_elements,
                "fingerprint": self.noise_fingerprint,
            },
            # 1e-3 is not exact in binary: the value that is really used is the float32 one, and it is derived here
            # so that it can never disagree with sigma
            "perturbation": {"sigma": self.sigma, "sigma_float32": float(np.float32(self.sigma))},
            "update": {**UPDATE_RECIPE, "reward_eta": self.reward_eta},
            "workload": {"hash": self.workload_hash, "generation_config_sha256": self.generation_config_sha256,
                         **({} if self.eval_dtype == LEGACY_EVAL_DTYPE else {"eval_dtype": self.eval_dtype})},
        }

    @property
    def hash(self) -> str:
        return canonical_json_hash(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict) -> "Recipe":
        _check_keys("recipe", data, {"manifest_version", "model", "noise", "perturbation", "update", "workload"})
        if data["manifest_version"] != MANIFEST_VERSION:
            raise ValueError(f"unknown manifest version {data['manifest_version']}")
        _check_keys("recipe.model", data["model"], {"id", "revision", "tokenizer_revision", "dtype", "schema_hash"})
        _check_keys("recipe.noise", data["noise"], {"engine_version", "chunk_elements", "fingerprint"})
        _check_keys("recipe.perturbation", data["perturbation"], {"sigma", "sigma_float32"})
        _check_keys("recipe.update", data["update"], {*UPDATE_RECIPE, "reward_eta"})
        _check_keys("recipe.workload", data["workload"], {"hash", "generation_config_sha256"} | ({"eval_dtype"} & set(data["workload"])))
        for key, value in UPDATE_RECIPE.items():
            if data["update"][key] != value:
                raise ValueError(f"recipe.update.{key} is {data['update'][key]!r}, manifest v1 says {value!r}")
        recipe = cls(
            model_id=data["model"]["id"],
            model_revision=data["model"]["revision"],
            tokenizer_revision=data["model"]["tokenizer_revision"],
            dtype=data["model"]["dtype"],
            schema_hash=data["model"]["schema_hash"],
            engine_version=data["noise"]["engine_version"],
            chunk_elements=data["noise"]["chunk_elements"],
            noise_fingerprint=data["noise"]["fingerprint"],
            sigma=data["perturbation"]["sigma"],
            reward_eta=data["update"]["reward_eta"],
            workload_hash=data["workload"]["hash"],
            generation_config_sha256=data["workload"]["generation_config_sha256"],
            eval_dtype=data["workload"].get("eval_dtype", LEGACY_EVAL_DTYPE),
        )
        if recipe.to_dict() != data:
            raise ValueError("recipe does not round-trip (a derived value, such as sigma_float32, disagrees)")
        return recipe


@dataclass(frozen=True)
class CandidateDescriptor:
    """
    One logical candidate: which recipe, which parent weights, which seed. Small on purpose.
    Operational data (worker, attempt, lease, retry, reward, time) has no field here: it belongs to the ledger,
    and noise must not depend on it. Passing such a field is a TypeError.
    """
    recipe_hash: str
    parent_weights_sha256: str   # the weights this candidate must be applied to (the model version)
    experiment_id: str
    generation: int
    index: int                   # position in the canonical candidate order of the generation
    seed: int

    def __post_init__(self):
        _check_text("recipe_hash", self.recipe_hash, _HEX64)
        _check_text("parent_weights_sha256", self.parent_weights_sha256, _HEX64)
        _check_text("experiment_id", self.experiment_id, _NAME)
        _check_int("generation", self.generation, 0)
        _check_int("index", self.index, 0)
        _check_int("seed", self.seed, 0, MAX_SEED)

    @property
    def candidate_id(self) -> str:
        """Identity of the logical job: the same for every attempt and every worker."""
        return f"{self.experiment_id}/g{self.generation}/c{self.index}"

    def to_dict(self) -> dict:
        return {
            "recipe_hash": self.recipe_hash,
            "parent_weights_sha256": self.parent_weights_sha256,
            "experiment_id": self.experiment_id,
            "generation": self.generation,
            "index": self.index,
            "seed": self.seed,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CandidateDescriptor":
        _check_keys("candidate descriptor", data, {
            "recipe_hash", "parent_weights_sha256", "experiment_id", "generation", "index", "seed"})
        return cls(**data)


def derive_seed(experiment_id: str, generation: int, index: int) -> int:
    """
    A seed for candidate `index` of `generation`, the same every time, different for every generation.

    This is the coordinator's way of CHOOSING seeds, not a rule the workers have to know: seeds travel
    explicitly in the candidate descriptors. 52 bits of SHA-256, so every seed is below MAX_SEED and a
    duplicate inside a generation is practically impossible (and would be refused by the update).
    """
    _check_text("experiment_id", experiment_id, _NAME)
    _check_int("generation", generation, 0)
    _check_int("index", index, 0)
    digest = hashlib.sha256(f"heteroes-seed-v1|{experiment_id}|{generation}|{index}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "little") & (2**52 - 1)
