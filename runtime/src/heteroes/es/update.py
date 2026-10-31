from heteroes.model.schema import ParameterSchema, resolve_tensors
from heteroes.es.checks import (
    _check_param,
    _check_coefficients,
    check_update_inputs,
    UpdateReport,
    NonFiniteUpdateError,
)
from heteroes.noise.engine import num_chunks, generate_chunk_noise, chunk_length, generator_for_engine
from heteroes.noise.contracts import ParameterNoiseAddress, DEFAULT_CHUNK_ELEMENTS, ENGINE_VERSION, ENGINE_V2
from heteroes.noise import engine_v2_cuda
from heteroes.es import perturb as _perturb
from heteroes.noise.parallel import ordered_map, noise_threads

import math
import torch
import torch.nn as nn
import numpy as np


DEFAULT_ETA = 1e-9
# engine v2 on the GPU: the noise of this many candidates is made in one launch (memory about 12 bytes per element)
SEEDS_PER_LAUNCH = 4


def standardize_rewards(rewards, eta=DEFAULT_ETA) -> np.ndarray:
    if not (math.isfinite(eta) and eta > 0):
        raise ValueError("eta must finite and > 0")

    # calculate in float64 then cast to float32
    rewards = np.asarray(rewards, dtype=np.float64)
    if rewards.ndim != 1:
        raise ValueError("rewards must be 1d-array")
    if not rewards.size > 0:
        raise ValueError("rewards size must > 0")
    if not np.isfinite(rewards).all():
        raise ValueError("rewards has value being Nan/Inf")

    # z = (r - mean(r)) / (std(r) + eta)
    mean_r = rewards.mean(dtype=np.float64)
    std_r = rewards.std(ddof=0, dtype=np.float64)

    # no signal
    if std_r < eta:
        return np.zeros(rewards.size, dtype=np.float32)

    z = (rewards - mean_r) / (std_r + np.float64(eta))

    return z.astype(np.float32)


def apply_coefficients_(
    model: nn.Module,
    schema: ParameterSchema,
    candidate_seeds: list[int],
    coefficients,
    alpha: float,
    chunk_elements: int = DEFAULT_CHUNK_ELEMENTS,
    *,
    engine: str = ENGINE_VERSION,
) -> UpdateReport:
    """
    The update of one ES generation with the coefficients GIVEN (no standardization here): what a worker applies when it
    replays a generation record. `apply_es_update_` is this with the coefficients computed from the rewards.
    """
    tensors = resolve_tensors(model, schema)
    for tensor in tensors:
        _check_param(tensor)
    return _apply_coefficients(
        schema, tensors, candidate_seeds, _check_coefficients(coefficients), alpha, chunk_elements, engine
    )


# agentic esopt update style
def apply_es_update_(
    model: nn.Module,
    schema: ParameterSchema,
    candidate_seeds: list[int],
    rewards,
    alpha: float,
    chunk_elements: int = DEFAULT_CHUNK_ELEMENTS,
    eta=DEFAULT_ETA,
    *,
    engine: str = ENGINE_VERSION,
) -> UpdateReport:
    # resolve tensor
    tensors = resolve_tensors(model, schema)
    # check param
    for tensor in tensors:
        _check_param(tensor)

    # z already check eta and rewards
    z_rewards = standardize_rewards(rewards, eta)
    return _apply_coefficients(schema, tensors, candidate_seeds, z_rewards, alpha, chunk_elements, engine)


def _apply_coefficients(
    schema: ParameterSchema,
    tensors,
    candidate_seeds,
    z_rewards,
    alpha: float,
    chunk_elements: int,
    engine: str = ENGINE_VERSION,
) -> UpdateReport:
    generate = generate_chunk_noise if engine == ENGINE_VERSION else generator_for_engine(engine)
    total_numel = sum(t.numel() for t in tensors)

    noop = check_update_inputs(candidate_seeds, z_rewards, alpha, total_numel, chunk_elements)
    if noop is not None:
        return noop

    schema_hash = schema.hash
    n_seeds = len(candidate_seeds)
    # The update is elementwise, so consecutive chunks of a tensor can be processed as ONE piece of up to BATCH_ELEMENTS elements:
    # the bits do not depend on the piece size, and one launch per operation per piece instead of per chunk of 2**18 elements saves
    # most of the Python and kernel-launch overhead. The noise itself is still generated chunk by chunk (its identity is the chunk).
    group_chunks = max(1, _perturb.BATCH_ELEMENTS // chunk_elements)

    # Every (tensor, group of chunks, candidate, chunk) noise block, in the order the consumer needs them. They are generated on a
    # thread pool but come back in this order, so the sum over candidates (the only floating-point order that matters, element by
    # element: candidate 0 first) is the same as with one thread and one chunk at a time.
    def tasks():
        for entry, tensor in zip(schema.entries, tensors):
            numel = tensor.numel()
            n_chunks = num_chunks(numel=numel, chunk_elements=chunk_elements)
            for first in range(0, n_chunks, group_chunks):
                for seed in candidate_seeds:
                    for chunk_index in range(first, min(first + group_chunks, n_chunks)):
                        address = ParameterNoiseAddress(
                            candidate_seed=seed,
                            schema_hash=schema_hash,
                            parameter_index=entry.index,
                            chunk_elements=chunk_elements,
                        ).chunk(chunk_index)
                        yield address, chunk_length(numel, chunk_index, chunk_elements)

    # Engine v2 can be made on the coordinator's GPU itself, with the same bits (engine_v2_cuda); then no CPU stream.
    on_device = (
        engine == ENGINE_V2
        and bool(tensors)
        and all(engine_v2_cuda.enabled(device) for device in {t.device for t in tensors})
    )
    if not on_device:
        noise_stream = ordered_map(lambda task: generate(*task), tasks(), threads=noise_threads(engine))

    # The three statistics of a piece stay on the device and are read once at the end (one sync instead of three per chunk).
    changed_parts, requested_parts, applied_parts = [], [], []
    finite_parts = []
    with torch.no_grad():
        for entry, tensor in zip(schema.entries, tensors):
            numel = tensor.numel()
            n_chunks = num_chunks(numel=numel, chunk_elements=chunk_elements)
            for first in range(0, n_chunks, group_chunks):
                last = min(first + group_chunks, n_chunks)
                start = first * chunk_elements
                n = min(numel, last * chunk_elements) - start
                chunk = tensor.view(-1)[start : start + n]
                acc = torch.zeros(n, dtype=torch.float32, device=tensor.device)

                made = []
                for position, (seed, zi) in enumerate(zip(candidate_seeds, z_rewards)):
                    if on_device:
                        if not made:  # the noise of the next few candidates in one launch; still summed in order
                            batch = candidate_seeds[position : position + SEEDS_PER_LAUNCH]
                            indices = range(first, last)
                            lengths = [chunk_length(numel, i, chunk_elements) for i in indices]
                            addresses = [
                                ParameterNoiseAddress(
                                    candidate_seed=s,
                                    schema_hash=schema_hash,
                                    parameter_index=entry.index,
                                    chunk_elements=chunk_elements,
                                ).chunk(i)
                                for s in batch
                                for i in indices
                            ]
                            made = list(
                                engine_v2_cuda.generate_chunks(addresses, lengths * len(batch), tensor.device)
                                .view(len(batch), n)
                                .unbind(0)
                            )
                        eps = made.pop(0).to(torch.float32)
                    else:
                        parts = [next(noise_stream) for _ in range(last - first)]
                        eps = parts[0] if len(parts) == 1 else np.concatenate(parts)
                        # fp16 to the device first, then widen there: widening on the CPU first costs a single-threaded
                        # cast of every element
                        eps = torch.from_numpy(eps).to(device=tensor.device).to(torch.float32)

                    term = eps * float(zi)
                    acc = acc + term

                # Explicit float32 reciprocal on every device; never rely on a framework's scalar-division lowering.
                direction = acc * float(np.float32(1) / np.float32(n_seeds))
                update = direction * float(np.float32(alpha))
                new = (chunk.to(torch.float32) + update).to(torch.float16)
                finite = torch.isfinite(new).all()
                if tensor.is_cuda:
                    finite_parts.append(finite)
                elif not finite.item():
                    raise NonFiniteUpdateError("updated weights must be finite")
                # compare

                changed_parts.append((new.view(torch.int16) != chunk.view(torch.int16)).sum())
                requested_parts.append((update.double() ** 2).sum())
                applied_parts.append(((new.double() - chunk.double()) ** 2).sum())

                chunk.copy_(new)

        if finite_parts and not torch.stack(finite_parts).all().item():
            raise NonFiniteUpdateError("updated weights must be finite; model must be restored from checkpoint")
        changed = 0
        requested_l2 = 0.0
        applied_l2 = 0.0
        if changed_parts:
            for value in torch.stack(changed_parts).tolist():
                changed += int(value)
            for value in torch.stack(requested_parts).tolist():
                requested_l2 += float(value)
            for value in torch.stack(applied_parts).tolist():
                applied_l2 += float(value)

    requested_l2 = math.sqrt(requested_l2)
    applied_l2 = math.sqrt(applied_l2)
    coefficients = tuple(float(v) for v in z_rewards)

    return UpdateReport(
        noop=False,
        coefficients=coefficients,
        requested_l2=requested_l2,
        applied_l2=applied_l2,
        changed=changed,
        numel=total_numel,
    )
