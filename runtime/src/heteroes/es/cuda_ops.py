"""
Perturbation and update with the noise of the CUDA engine (`noise/cuda_engine.py`), G7.

The arithmetic is exactly that of the contract and of `perturb.py` / `update.py` (O2 = c, O4, FP32 accumulation in candidate order);
only where the noise comes from changes: it is made on the device, so nothing goes through the CPU and there is no thread pool.

  perturb:  param <- fp16( fp32(param) + fp32(sigma) * fp32(eps) )                         (two separate operations)
  update:   acc = sum over candidates, in order, of fp32(eps_i) * z_i   (each product and each sum separate)
            param <- fp16( fp32(param) + (acc / n) * fp32(alpha) )

The restore is NOT here: it stays the verified restore from the snapshot (`snapshot.py`), which does not depend on the noise.
"""

import math

import numpy as np
import torch

from heteroes.es.checks import _check_param, _check_param_sigma, check_update_inputs
from heteroes.es.update import UpdateReport, _check_coefficients, NonFiniteUpdateError
from heteroes.noise.contracts import check_seed
from heteroes.model.schema import ParameterSchema, resolve_tensors
from heteroes.noise.cuda_engine import PIECE_ELEMENTS, TensorNoise, check_device


def _check_cuda(tensors) -> None:
    for tensor in tensors:
        if tensor.device.type != "cuda":
            raise ValueError(f"the CUDA noise engine needs the weights on a CUDA device, got {tensor.device}")
        check_device(tensor.device)


def perturb_model_cuda_(model: torch.nn.Module, schema: ParameterSchema, candidate_seed: int, sigma: float) -> None:
    """
    Perturb every tensor in place with the noise of the CUDA engine. Everything that can be checked is checked before the first write
    (as `perturb_model_`); a failure while writing (for example out of memory) leaves the model half perturbed, so the caller restores.
    """
    check_seed(candidate_seed)
    tensors = resolve_tensors(model, schema)
    for tensor in tensors:
        _check_param_sigma(tensor, sigma)
    _check_cuda(tensors)
    sigma32 = float(np.float32(sigma))
    schema_hash = schema.hash
    with torch.no_grad():
        for entry, tensor in zip(schema.entries, tensors, strict=True):
            flat = tensor.view(-1)
            noise = TensorNoise(schema_hash, candidate_seed, entry.index, flat.numel(), tensor.device)
            while noise.done < noise.numel:
                start = noise.done
                piece = noise.next(min(PIECE_ELEMENTS, noise.numel - start))
                part = flat[start : start + piece.numel()]
                scaled = piece.to(torch.float32) * sigma32
                part.copy_((part.to(torch.float32) + scaled).to(torch.float16))


def apply_coefficients_cuda_(
    model: torch.nn.Module, schema: ParameterSchema, candidate_seeds, coefficients, alpha: float
) -> UpdateReport:
    """The update of one generation with the coefficients given (see `apply_coefficients_`), with the noise of the CUDA engine."""
    tensors = resolve_tensors(model, schema)
    for tensor in tensors:
        _check_param(tensor)
    _check_cuda(tensors)
    z_rewards = _check_coefficients(coefficients)
    total_numel = sum(t.numel() for t in tensors)
    noop = check_update_inputs(candidate_seeds, z_rewards, alpha, total_numel)
    if noop is not None:
        return noop

    schema_hash = schema.hash
    n_seeds = len(candidate_seeds)
    alpha32 = float(np.float32(alpha))
    inv_n32 = float(np.float32(1) / np.float32(n_seeds))
    changed_parts, requested_parts, applied_parts = [], [], []
    finite_parts = []
    with torch.no_grad():
        for entry, tensor in zip(schema.entries, tensors, strict=True):
            flat = tensor.view(-1)
            streams = [
                TensorNoise(schema_hash, int(seed), entry.index, flat.numel(), tensor.device)
                for seed in candidate_seeds
            ]
            while streams[0].done < flat.numel():
                start = streams[0].done
                count = min(PIECE_ELEMENTS, flat.numel() - start)
                chunk = flat[start : start + count]
                acc = torch.zeros(count, dtype=torch.float32, device=tensor.device)
                for stream, zi in zip(streams, z_rewards):
                    eps = stream.next(count).to(torch.float32)
                    term = eps * float(zi)
                    acc = acc + term
                direction = acc * inv_n32
                update = direction * alpha32
                new = (chunk.to(torch.float32) + update).to(torch.float16)
                finite_parts.append(torch.isfinite(new).all())
                changed_parts.append((new.view(torch.int16) != chunk.view(torch.int16)).sum())
                requested_parts.append((update.double() ** 2).sum())
                applied_parts.append(((new.double() - chunk.double()) ** 2).sum())
                chunk.copy_(new)
        if finite_parts and not torch.stack(finite_parts).all().item():
            raise NonFiniteUpdateError("updated weights must be finite; model must be restored from checkpoint")
        changed = sum(int(v) for v in torch.stack(changed_parts).tolist())
        requested_l2 = math.sqrt(sum(float(v) for v in torch.stack(requested_parts).tolist()))
        applied_l2 = math.sqrt(sum(float(v) for v in torch.stack(applied_parts).tolist()))
    return UpdateReport(
        noop=False,
        coefficients=tuple(float(v) for v in z_rewards),
        requested_l2=requested_l2,
        applied_l2=applied_l2,
        changed=changed,
        numel=total_numel,
    )
