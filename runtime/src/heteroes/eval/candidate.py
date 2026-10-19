import hashlib
import time
from dataclasses import asdict

import numpy as np
import torch

from heteroes.es.perturb import perturb_model_
from heteroes.es.snapshot import restore_from_snapshot_, take_snapshot
from heteroes.eval.generate import evaluate_model
from heteroes.eval.workload import workload_hash
from heteroes.model.schema import ParameterSchema, resolve_tensors
from heteroes.noise.contracts import DEFAULT_CHUNK_ELEMENTS, ENGINE_VERSION


def tensors_sha256(tensors) -> str:
    """The `model_weights_sha256` of tensors that are already in canonical order (for example the tensors of a snapshot)."""
    digest = hashlib.sha256()
    for tensor in tensors:
        digest.update(tensor.detach().reshape(-1).view(torch.int16).cpu().numpy())      # a buffer: no extra copy to bytes
    return digest.hexdigest()


def model_weights_sha256(model, schema: ParameterSchema) -> str:
    """
    SHA-256 of the raw bits of every tensor, in canonical (schema) order.

    The bits are read as int16 so that NaN and the sign of zero count; a tied tensor appears once.
    This is a fingerprint of the weights, not of the layout (that is schema.hash).
    """
    digest = hashlib.sha256()
    for tensor in resolve_tensors(model, schema):
        digest.update(tensor.detach().reshape(-1).view(torch.int16).cpu().numpy())      # a buffer: no extra copy to bytes
    return digest.hexdigest()


def _evaluation_as_dict(result) -> dict:
    return {"mean_reward": result.mean_reward, "records": [asdict(record) for record in result.records]}


def run_candidate(
    model,
    tokenizer,
    schema: ParameterSchema,
    seed: int,
    sigma: float,
    chunk_elements: int = DEFAULT_CHUNK_ELEMENTS,
) -> dict:
    """
    The whole life of one ES candidate on one machine, and a record of it:

        fingerprint -> snapshot -> evaluate the base model
        -> perturb -> fingerprint -> evaluate the candidate      (restore always runs after this)
        -> restore (verified bit for bit) -> fingerprint -> evaluate again

    Returns a dict of plain JSON types. If anything fails, the error is raised (never turned into a
    reward of 0). If the failure happens after the perturbation, the model is restored first; if that
    restore itself fails (RestoreError) the weights are unreliable and the worker must not be used again.
    """
    timing: dict[str, float] = {}

    def timed(name, function, *args, **kwargs):
        start = time.perf_counter()
        value = function(*args, **kwargs)
        timing[name] = time.perf_counter() - start
        return value

    device = next(model.parameters()).device
    on_gpu = device.type == "cuda"
    if on_gpu:
        torch.cuda.synchronize(device)
        torch.cuda.reset_peak_memory_stats(device)
        baseline_allocated = torch.cuda.memory_allocated(device)

    original_digest = timed("hash_original", model_weights_sha256, model, schema)
    snapshot = timed("snapshot", take_snapshot, model, schema)
    base = timed("evaluate_base", evaluate_model, model, tokenizer)

    try:
        timed("perturb", perturb_model_, model, schema, seed, sigma, chunk_elements)
        perturbed_digest = timed("hash_perturbed", model_weights_sha256, model, schema)
        candidate = timed("evaluate_candidate", evaluate_model, model, tokenizer)
    finally:
        # also when the perturbation or the evaluation failed halfway: the model must come back
        timed("restore", restore_from_snapshot_, model, schema, snapshot)

    restored_digest = timed("hash_restored", model_weights_sha256, model, schema)
    restored = timed("evaluate_restored", evaluate_model, model, tokenizer)

    gpu_memory = None
    if on_gpu:
        torch.cuda.synchronize(device)
        gpu_memory = {
            "baseline_allocated_bytes": baseline_allocated,
            "peak_allocated_bytes": torch.cuda.max_memory_allocated(device),
        }

    return {
        "seed": seed,
        "sigma": sigma,
        "sigma_float32": float(np.float32(sigma)),
        "chunk_elements": chunk_elements,
        "schema_hash": schema.hash,
        "engine_version": ENGINE_VERSION,
        "workload_hash": workload_hash(),
        "weights_sha256": {"original": original_digest, "perturbed": perturbed_digest, "restored": restored_digest},
        "restored_equals_original": restored_digest == original_digest,
        "evaluation": {
            "base": _evaluation_as_dict(base),
            "candidate": _evaluation_as_dict(candidate),
            "restored": _evaluation_as_dict(restored),
        },
        "timing_seconds": timing,
        "gpu_memory": gpu_memory,
    }
