"""Experimental vendor-FP16 projection fast path over the strict decode graph.

This backend keeps the strict RMSNorm, RoPE, attention, packed-cache and greedy operators but replaces every
projection by ``torch.nn.functional.linear`` on the live FP16 parameters. Q/K/V and gate/up groups are merged
into single column blocks once, following the same weight-concatenation layout used by serving engines.

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

FP16_GRAPH_BACKEND = "decoder_vendor_fp16_gemm_cuda_graph_v1_experimental"
FP16_PROJECTION = "vendor_fp16_linear_v1_experimental"


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
            "fp16DecoderSourceSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "hardwareQualified": False,
        }
        self.fingerprint = canonical_json_hash(self.identity)

    def _merge(self, modules):
        key = tuple(id(module) for module in modules)
        biases = tuple(getattr(module, "bias", None) for module in modules)
        if any(bias is not None for bias in biases) and any(bias is None for bias in biases):
            self._merged[key] = None
            return
        weight = torch.cat([module.weight for module in modules], dim=0).contiguous()
        bias = None if biases[0] is None else torch.cat(biases, dim=0).contiguous()
        self._merged[key] = (weight, bias, tuple(module.weight.shape[0] for module in modules))

    def _merged_group(self, modules):
        key = tuple(id(module) for module in modules)
        if key not in self._merged:
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
