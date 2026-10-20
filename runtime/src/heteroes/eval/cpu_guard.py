"""Versioned FP32 decoder with a selective CPU reference for near-tied greedy tokens.

The margin is empirical, not an error bound. Strict cross-device audits remain necessary.
Engine constants and reference arithmetic are part of this decoder's recipe identity.
"""

import copy
import ctypes
import inspect
from pathlib import Path
import sys
import time
import weakref

import torch
from torch.utils._python_dispatch import TorchDispatchMode
from transformers import LogitsProcessorList

from .compact_decode import UnsupportedDecode, decode_settings

MARGIN = 0.01
MAX_REFERENCE_BYTES = 8 * 2**30
RAM_RESERVE_BYTES = 512 * 2**20


class ReferenceUnavailable(RuntimeError):
    """The declared reference cannot be evaluated; never use an unchecked primary token."""


class FullPrecision(TorchDispatchMode):
    """Preserve FP64 through explicit FP32 casts inside the reference forward only."""

    def __torch_dispatch__(self, func, types, args=(), kwargs=None):
        kwargs = kwargs or {}
        if func == torch.ops.aten._to_copy.default and kwargs.get("dtype") == torch.float32:
            kwargs = {**kwargs, "dtype": torch.float64}
        return func(*args, **kwargs)


def available_memory_bytes():
    """Available physical RAM on the supported Linux/WSL and native Windows workers."""
    if sys.platform == "win32":

        class MemoryStatus(ctypes.Structure):
            _fields_ = [("length", ctypes.c_uint32), ("load", ctypes.c_uint32)] + [
                (name, ctypes.c_uint64)
                for name in (
                    "total",
                    "available",
                    "pageTotal",
                    "pageAvailable",
                    "virtual",
                    "virtualAvailable",
                    "extended",
                )
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            raise ReferenceUnavailable("Cannot determine available CPU RAM")
        return status.available
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            fields = line.split()
            if fields[0] == "MemAvailable:":
                return int(fields[1]) * 1024
    except (OSError, ValueError, IndexError) as error:
        raise ReferenceUnavailable("Cannot determine available CPU RAM") from error
    raise ReferenceUnavailable("Cannot determine available CPU RAM")


def reference_bytes(model):
    return sum(
        t.numel() * (8 if t.is_floating_point() else t.element_size()) for t in [*model.parameters(), *model.buffers()]
    )


def cpu_reference(model):
    """A fresh CPU copy of current candidate weights, without an extra GPU model allocation."""
    needed = reference_bytes(model)
    if needed > MAX_REFERENCE_BYTES:
        raise ReferenceUnavailable(f"CPU reference exceeds the {MAX_REFERENCE_BYTES}-byte parameter limit")
    if available_memory_bytes() < 2 * needed + RAM_RESERVE_BYTES:
        raise ReferenceUnavailable(f"Insufficient CPU RAM for a {needed}-byte reference and working reserve")
    # Deepcopy's memo preserves tied Parameter identities. Copy tensors directly to CPU, one at a time,
    # instead of first duplicating the entire FP32 model on the GPU. This copy is local to one generate call.
    memo = {}
    with torch.no_grad():
        for tensor in [*model.parameters(), *model.buffers()]:
            dtype = torch.float64 if tensor.is_floating_point() else tensor.dtype
            value = tensor.detach().to(device="cpu", dtype=dtype, copy=True)
            memo[id(tensor)] = (
                torch.nn.Parameter(value, requires_grad=False) if isinstance(tensor, torch.nn.Parameter) else value
            )
    reference = copy.deepcopy(model, memo).eval()
    if any(p.device.type != "cpu" or p.dtype != torch.float64 for p in reference.parameters()):
        raise ReferenceUnavailable("CPU reference has unsupported parameter placement or precision")
    # A bound method captured by a wrapper stored on its model creates a cycle holding several GB.
    # Keep its signature for HF validation, but only a weak method reference for dispatch.
    signature = inspect.signature(reference.forward)
    forward = weakref.WeakMethod(reference.forward)

    def precise_forward(*args, **kwargs):
        target = forward()
        if target is None:
            raise ReferenceUnavailable("CPU reference was released")
        with FullPrecision():
            return target(*args, **kwargs)

    precise_forward.__signature__ = signature
    reference.forward = precise_forward
    return reference


class MarginProcessor:
    def __init__(self, reference, prompt_length, eos_ids):
        self.reference = reference
        self.prompt_length = prompt_length
        self.eos_ids = eos_ids
        self.reference_calls = 0

    def __call__(self, input_ids, scores):
        values = scores.topk(2, dim=-1).values
        if not torch.isfinite(values).all():
            raise ReferenceUnavailable("Greedy scores must be finite")
        active = torch.ones(scores.shape[0], dtype=torch.bool, device=scores.device)
        for eos in self.eos_ids:
            active &= ~(input_ids[:, self.prompt_length :] == eos).any(dim=-1)
        rows = torch.where(active & (values[:, 0] - values[:, 1] < MARGIN))[0].tolist()
        result = scores.clone()
        for row in rows:
            checked = self.reference(row, input_ids[row : row + 1]).to(device=scores.device, dtype=scores.dtype)
            if checked.shape != result[row].shape or not torch.isfinite(checked).all():
                raise ReferenceUnavailable("CPU reference scores must be finite and match the vocabulary")
            result[row] = checked
            self.reference_calls += 1
        return result


def guarded_generate_ids(model, input_ids, attention_mask, max_new_tokens):
    """HF greedy generation in FP32; CPU FP64 recomputes ambiguous rows from their complete prefix.

    Only the repetition-penalty processor is supported, as checked before generating. A new CPU model
    is created lazily per call, so another candidate's weights can never leak into the reference.
    CPU scores go through HF's normal FP32 output conversion and processors exactly once.
    """
    if model.training or any(p.dtype != torch.float32 for p in model.parameters()):
        raise ValueError("The CPU-guard decoder requires an evaluation model with FP32 parameters")
    config = model.generation_config
    if (
        config.num_beams not in (None, 1)
        or config.num_return_sequences not in (None, 1)
        or config.max_time is not None
        or config.stop_strings is not None
        or config.token_healing
        or config.cache_implementation not in (None, "dynamic")
    ):
        raise UnsupportedDecode("The CPU-guard decoder requires plain greedy generation and a dynamic cache")
    eos_ids, _, _ = decode_settings(model, max_new_tokens)
    prompt_length = input_ids.shape[1]
    original_mask = attention_mask.detach().cpu()
    reference = None
    stats = {"referenceCalls": 0, "referenceBytes": 0, "referenceSeconds": 0.0}

    def recompute(row, prefix):
        nonlocal reference
        started = time.perf_counter()
        if reference is None:
            reference = cpu_reference(model)
            stats["referenceBytes"] = reference_bytes(reference)
        steps = prefix.shape[1] - prompt_length
        mask = torch.cat([original_mask[row : row + 1], original_mask.new_ones((1, steps))], dim=-1)
        reply = reference.generate(
            input_ids=prefix.cpu(),
            attention_mask=mask,
            max_new_tokens=1,
            do_sample=False,
            return_dict_in_generate=True,
            output_scores=True,
        )
        stats["referenceSeconds"] += time.perf_counter() - started
        return reply.scores[0][0]

    guard = MarginProcessor(recompute, prompt_length, eos_ids)
    with torch.no_grad():
        ids = model.generate(
            input_ids=input_ids,
            attention_mask=attention_mask,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            logits_processor=LogitsProcessorList([guard]),
            return_dict_in_generate=False,
        )
    stats["referenceCalls"] = guard.reference_calls
    return ids, stats
