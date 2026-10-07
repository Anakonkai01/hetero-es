"""
Loading the pinned Qwen checkpoint and describing it as a `Recipe` (manifest v1): what the worker and the coordinator both need
before they can take part in an experiment. The same logic as `scripts/run_one_candidate.py`, whose recorded recipe hash is the
test that the two agree.
"""
import time
from dataclasses import dataclass
from pathlib import Path

from heteroes.es.update import DEFAULT_ETA
from heteroes.eval.workload import workload_hash
from heteroes.manifest import DEFAULT_EVAL_DTYPE, Recipe, generation_config_sha256
from heteroes.model.schema import ParameterSchema, build_parameter_schema
from heteroes.noise.contracts import DEFAULT_CHUNK_ELEMENTS, ENGINE_VERSION
from heteroes.noise.selftest import EXPECTED_NOISE_FINGERPRINT, compute_noise_fingerprint

PINNED_REVISION = "7ae557604adf67be50417f59c2c2f167def9a775"
MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"


@dataclass
class LoadedModel:
    model: object
    tokenizer: object
    schema: ParameterSchema
    revision: str
    generation_config: dict
    device: str


def check_noise_selftest() -> float:
    """This machine must generate the canonical noise bytes, or nothing it computes can be trusted. Returns the seconds it took."""
    start = time.perf_counter()
    if compute_noise_fingerprint() != EXPECTED_NOISE_FINGERPRINT:
        raise RuntimeError("the noise self-test failed: this NumPy does not generate the canonical noise bytes")
    return time.perf_counter() - start


def load_pinned_model(model_path, device: str) -> LoadedModel:
    """The checkpoint in `model_path` (a directory named after the pinned revision), in FP16, on `device`."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    path = Path(model_path)
    revision = path.resolve().name
    if revision != PINNED_REVISION:
        raise ValueError(f"the model directory must be named after the pinned revision {PINNED_REVISION}, got '{revision}'")
    if not path.is_dir():
        raise FileNotFoundError(path)
    model = AutoModelForCausalLM.from_pretrained(path, dtype=torch.float16).to(device)
    tokenizer = AutoTokenizer.from_pretrained(path)
    return LoadedModel(model, tokenizer, build_parameter_schema(model), revision, model.generation_config.to_dict(), device)


def build_recipe(loaded: LoadedModel, sigma: float, chunk_elements: int = DEFAULT_CHUNK_ELEMENTS, reward_eta: float = DEFAULT_ETA,
                 eval_dtype: str = DEFAULT_EVAL_DTYPE) -> Recipe:
    return Recipe(
        model_id=MODEL_ID,
        model_revision=loaded.revision,
        tokenizer_revision=loaded.revision,        # the tokenizer files come from the same snapshot directory
        dtype=str(next(loaded.model.parameters()).dtype),
        schema_hash=loaded.schema.hash,
        engine_version=ENGINE_VERSION,
        chunk_elements=chunk_elements,
        noise_fingerprint=EXPECTED_NOISE_FINGERPRINT,
        sigma=sigma,
        reward_eta=reward_eta,
        workload_hash=workload_hash(),
        generation_config_sha256=generation_config_sha256(loaded.generation_config),
        eval_dtype=eval_dtype,
    )
