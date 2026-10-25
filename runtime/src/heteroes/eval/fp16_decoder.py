"""Experimental vendor-FP16 projection fast path over the strict decode graph.

This backend keeps the strict RMSNorm, RoPE, attention, packed-cache and greedy operators but replaces every
projection by ``torch.nn.functional.linear`` on the live FP16 parameters. Q/K/V and gate/up parameters are
views of shared column blocks, so in-place ES writes and restoration also update the merged GEMM operands.

The result is NOT the exact integer identity: the projection accumulates in the vendor FP16 tensor-core order
instead of reproducing FP16 products through the B22 integer limbs. It exists to measure how much of the gap to
vLLM is the exact projection kernel and how much is the rest of the graph. It is opt-in, unqualified and never
selected silently.
"""

from __future__ import annotations

import hashlib
from itertools import chain
from pathlib import Path

import torch
import torch.nn.functional as F

from heteroes.canonical import canonical_json_hash
from heteroes.eval.reference_ops import ReferenceArithmeticError
from heteroes.eval.strict_decoder_graph import DEFAULT_GRAPH_BYTES, StrictDecoderGraph

FP16_GRAPH_BACKEND = "decoder_vendor_fp16_gemm_cuda_graph_v2_experimental"
FP16_PROJECTION = "vendor_fp16_live_linear_v2_experimental"


@torch.no_grad()
def bind_merged_parameters(parameters):
    """Bind disjoint parameters into one allocation, preserving objects, shapes and published bits.

    Already adjacent views reuse their storage. Overlapping or mixed layouts fail before any write.
    This is model preparation, before capture; it is not an inference-time prepared-weight cache.
    """
    parameters = tuple(parameters)
    if not parameters or any(
        not isinstance(p, torch.nn.Parameter) or p.ndim not in (1, 2) or not p.numel() for p in parameters
    ):
        raise ReferenceArithmeticError("Merged parameters need a nonempty vector/matrix group")
    first = parameters[0]
    if any(
        p.ndim != first.ndim
        or p.shape[1:] != first.shape[1:]
        or p.dtype != first.dtype
        or p.device != first.device
        or not p.is_contiguous()
        for p in parameters
    ):
        raise ReferenceArithmeticError("Merged parameters need matching contiguous layouts")
    ranges = [(p.data_ptr(), p.data_ptr() + p.numel() * p.element_size()) for p in parameters]
    if any(a < d and c < b for i, (a, b) in enumerate(ranges) for c, d in ranges[i + 1 :]):
        raise ReferenceArithmeticError("Merged parameters must not overlap")
    shape = (sum(p.shape[0] for p in parameters), *first.shape[1:])
    if all(p.untyped_storage().data_ptr() == first.untyped_storage().data_ptr() for p in parameters) and all(
        ranges[i][1] == ranges[i + 1][0] for i in range(len(parameters) - 1)
    ):
        return first.as_strided(shape, first.stride())
    merged = torch.cat(parameters, dim=0).contiguous()
    for parameter, view in zip(parameters, merged.split([p.shape[0] for p in parameters]), strict=True):
        parameter.set_(view)
    return merged


class Fp16DecoderGraph(StrictDecoderGraph):
    """Captured decode with vendor FP16 projections; not an exact-integer or managed backend."""

    def __init__(
        self,
        model,
        *,
        max_context=256,
        allow_fixture=False,
        max_graph_bytes=DEFAULT_GRAPH_BYTES,
    ):
        self._merged = {}
        self._merged_signatures = {}
        super().__init__(
            model,
            max_context=max_context,
            allow_fixture=allow_fixture,
            max_graph_bytes=max_graph_bytes,
        )
        groups = []
        for index, layer in enumerate(model.model.layers):
            groups.append(
                (
                    f"model.layers.{index}.self_attn.q_proj",
                    f"model.layers.{index}.self_attn.k_proj",
                    f"model.layers.{index}.self_attn.v_proj",
                )
            )
            groups.append(
                (
                    f"model.layers.{index}.mlp.gate_proj",
                    f"model.layers.{index}.mlp.up_proj",
                )
            )
        for names in groups:
            self._merge(tuple(model.get_submodule(name) for name in names))
        self.identity = {
            **self.identity,
            "backend": FP16_GRAPH_BACKEND,
            "projectionImplementation": {
                "operator": FP16_PROJECTION,
                "call": "torch.nn.functional.linear",
                "torch": torch.__version__,
                "activation": "float32 rounded to float16",
                "weight": "live float16 parameter",
                "accumulation": "vendor float16 tensor-core",
                "exactIntegerIdentity": False,
            },
            "mergedGroups": [list(names) for names in groups],
            "weightStorage": "live_merged_parameter_views_v1",
            "fp16DecoderSourceSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "hardwareQualified": False,
        }
        self.fingerprint = canonical_json_hash(self.identity)

    def _merge(self, modules):
        key = tuple(id(module) for module in modules)
        biases = tuple(getattr(module, "bias", None) for module in modules)
        if any(bias is not None for bias in biases) and any(bias is None for bias in biases):
            self._merged[key] = None
            self._merged_signatures[key] = self._group_signature(modules)
            return
        parameters = tuple(module.weight for module in modules) + tuple(b for b in biases if b is not None)
        ids = {id(p) for p in parameters}
        ranges = [(p.data_ptr(), p.data_ptr() + p.numel() * p.element_size()) for p in parameters]
        # Preserve aliases outside this group. They keep the ordinary per-module GEMM execution.
        named = tuple(self.model.named_parameters(remove_duplicate=False))
        aliases = any(sum(id(other) == id(p) for _, other in named) != 1 for p in parameters)
        overlap = any(
            a < other.data_ptr() + other.numel() * other.element_size() and other.data_ptr() < b
            for a, b in ranges
            for _, other in named
            if id(other) not in ids
        )
        internal_overlap = any(a < d and c < b for i, (a, b) in enumerate(ranges) for c, d in ranges[i + 1 :])
        if aliases or overlap or internal_overlap:
            self._merged[key] = None
            self._merged_signatures[key] = self._group_signature(modules)
            return
        weight = bind_merged_parameters([module.weight for module in modules])
        bias = None if biases[0] is None else bind_merged_parameters(biases)
        self._merged[key] = (weight, bias, tuple(module.weight.shape[0] for module in modules))
        self._merged_signatures[key] = self._group_signature(modules)

    @staticmethod
    def _group_signature(modules):
        return tuple(
            None if p is None else (id(p), p.data_ptr(), tuple(p.shape), tuple(p.stride()), p.dtype, p.device)
            for module in modules
            for p in (module.weight, getattr(module, "bias", None))
        )

    def _merged_group(self, modules):
        key = tuple(id(module) for module in modules)
        if key not in self._merged or self._merged_signatures[key] != self._group_signature(modules):
            self._merge(modules)
        return self._merged[key]

    def buffers(self, *args, **kwargs):
        merged = chain(super().buffers(*args, **kwargs), (entry[0] for entry in self._merged.values() if entry))
        biases = (entry[1] for entry in self._merged.values() if entry and entry[1] is not None)
        return chain(merged, biases)

    @torch.inference_mode()
    def _project(self, value, module, flag):
        return F.linear(value.half(), module.weight, getattr(module, "bias", None)).float()

    @torch.inference_mode()
    def _project_many(self, value, modules, flag):
        modules = tuple(modules)
        merged = self._merged_group(modules)
        if merged is None:
            return tuple(self._project(value, module, flag) for module in modules)
        weight, bias, outputs = merged
        combined = F.linear(value.half(), weight, bias).float()
        return tuple(combined.split(outputs, dim=-1))


def static_identity():
    return {
        "backend": FP16_GRAPH_BACKEND,
        "operator": FP16_PROJECTION,
        "torch": torch.__version__,
        "sourceSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "hardwareQualified": False,
    }


def require_fp16_graph(model):
    """Explicit opt-in check for callers that construct this backend from a manifest."""
    if next(model.parameters()).dtype != torch.float16:
        raise ReferenceArithmeticError("The vendor FP16 fast path needs an FP16 model")
    return True
