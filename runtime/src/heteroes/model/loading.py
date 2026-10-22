"""
Loading the pinned Qwen checkpoint and describing it as a `Recipe` (manifest v1): what the worker and the coordinator both need
before they can take part in an experiment. The same logic as `scripts/run_one_candidate.py`, whose recorded recipe hash is the
test that the two agree.
"""

import time
from dataclasses import dataclass
from pathlib import Path

from heteroes.es.update import DEFAULT_ETA
from heteroes.eval.workloads import get_workload
from heteroes.manifest import DEFAULT_EVAL_DTYPE, Recipe, default_decode_engine, generation_config_sha256
from heteroes.model.schema import ParameterSchema, build_parameter_schema
from heteroes.noise.contracts import (
    CUDA_CALL_ELEMENTS,
    CUDA_ENGINE_VERSION,
    DEFAULT_CHUNK_ELEMENTS,
    ENGINE_VERSION,
    EXPECTED_CUDA_NOISE_FINGERPRINT,
)
from heteroes.noise.cuda_engine import check_cuda_noise_selftest
from heteroes.noise.selftest import EXPECTED_NOISE_FINGERPRINT, compute_noise_fingerprint
from heteroes.catalog import PINNED_MODEL_ID as MODEL_ID, PINNED_REVISION


@dataclass
class LoadedModel:
    model: object
    tokenizer: object
    schema: ParameterSchema
    revision: str
    generation_config: dict
    device: str
    model_id: str = MODEL_ID


def check_noise_selftest(engine: str = ENGINE_VERSION) -> float:
    """This machine must generate the canonical noise bytes, or nothing it computes can be trusted. Returns the seconds it took."""
    start = time.perf_counter()
    from heteroes.noise.contracts import ENGINE_V2, EXPECTED_V2_NOISE_FINGERPRINT

    if engine == ENGINE_VERSION:
        observed, expected = compute_noise_fingerprint(), EXPECTED_NOISE_FINGERPRINT
    elif engine == ENGINE_V2:
        from heteroes.noise.selftest_v2 import compute_noise_fingerprint as compute_v2

        observed, expected = compute_v2(), EXPECTED_V2_NOISE_FINGERPRINT
    else:
        raise ValueError(f"unknown CPU noise engine {engine!r}")
    if observed != expected:
        raise RuntimeError(f"the noise self-test failed for {engine}")
    return time.perf_counter() - start


def checked_cpu_noise_engines() -> dict[str, str]:
    """Advertise an engine only after its local known-answer test passes."""
    from heteroes.noise.contracts import CPU_NOISE_FINGERPRINTS

    for engine in CPU_NOISE_FINGERPRINTS:
        check_noise_selftest(engine)
    return dict(CPU_NOISE_FINGERPRINTS)


def load_pinned_model(model_path, device: str) -> LoadedModel:
    """The checkpoint in `model_path` (a directory named after the pinned revision), in FP16, on `device`."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    path = Path(model_path)
    revision = path.resolve().name
    if revision != PINNED_REVISION:
        raise ValueError(
            f"the model directory must be named after the pinned revision {PINNED_REVISION}, got '{revision}'"
        )
    if not path.is_dir():
        raise FileNotFoundError(path)
    model = AutoModelForCausalLM.from_pretrained(path, dtype=torch.float16).to(device)
    tokenizer = AutoTokenizer.from_pretrained(path)
    return LoadedModel(
        model, tokenizer, build_parameter_schema(model), revision, model.generation_config.to_dict(), device
    )


def check_recipe_selftest(recipe: Recipe, device: str) -> float:
    """The self-test of the noise engine that the recipe names, on this machine (the CUDA engine on `device`). Returns the seconds it took."""
    start = time.perf_counter()
    if recipe.engine_version == CUDA_ENGINE_VERSION:
        check_cuda_noise_selftest(device)
        return time.perf_counter() - start
    return check_noise_selftest(recipe.engine_version)


def build_recipe(
    loaded: LoadedModel,
    sigma: float,
    chunk_elements: int | None = None,
    reward_eta: float = DEFAULT_ETA,
    eval_dtype: str = DEFAULT_EVAL_DTYPE,
    noise_engine: str = "cpu",
    workload: str = "arith16",
    decode_engine: str | None = None,
) -> Recipe:
    """
    The recipe of an experiment from the loaded model and the choices. `noise_engine` is "cpu" (the canonical engine, `chunk_elements` its chunk,
    default 2**18) or "cuda" (the GPU engine of section 16 of the numerical contract: its call size is part of the engine, there is nothing to choose).
    """
    from heteroes.noise.contracts import ENGINE_V2, EXPECTED_V2_NOISE_FINGERPRINT

    if noise_engine == ENGINE_V2:
        engine_version, noise_chunk, fingerprint = (
            ENGINE_V2,
            DEFAULT_CHUNK_ELEMENTS if chunk_elements is None else chunk_elements,
            EXPECTED_V2_NOISE_FINGERPRINT,
        )
    elif noise_engine in ("cpu", ENGINE_VERSION):
        engine_version, noise_chunk, fingerprint = (
            ENGINE_VERSION,
            DEFAULT_CHUNK_ELEMENTS if chunk_elements is None else chunk_elements,
            EXPECTED_NOISE_FINGERPRINT,
        )
    elif noise_engine == "cuda":
        if chunk_elements is not None and chunk_elements != CUDA_CALL_ELEMENTS:
            raise ValueError(
                f"the CUDA noise engine has a fixed call size of {CUDA_CALL_ELEMENTS} elements, not {chunk_elements}"
            )
        engine_version, noise_chunk, fingerprint = (
            CUDA_ENGINE_VERSION,
            CUDA_CALL_ELEMENTS,
            EXPECTED_CUDA_NOISE_FINGERPRINT,
        )
    else:
        raise ValueError(f"unknown noise engine {noise_engine!r}: 'cpu' or 'cuda'")
    chosen = get_workload(workload)
    if decode_engine is None:
        decode_engine = default_decode_engine(
            chosen.name
        )  # None: the default of a new experiment (the compacting decoder on the long workloads)
    return Recipe(
        model_id=loaded.model_id,
        model_revision=loaded.revision,
        tokenizer_revision=loaded.revision,  # the tokenizer files come from the same snapshot directory
        dtype=str(next(loaded.model.parameters()).dtype),
        schema_hash=loaded.schema.hash,
        engine_version=engine_version,
        chunk_elements=noise_chunk,
        noise_fingerprint=fingerprint,
        sigma=sigma,
        reward_eta=reward_eta,
        workload_hash=chosen.hash(),
        generation_config_sha256=generation_config_sha256(loaded.generation_config),
        eval_dtype=eval_dtype,
        workload_name=chosen.name,
        decode_engine=decode_engine,
    )
