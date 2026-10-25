"""Experimental graph composition with a NEW row-scaled integer linear contract and strict FP32 nonlinearities.

No managed recipe/default is changed. These adapters share the existing restricted architecture validation,
generation rules, original FP16 weights and bounded decode ownership. They cannot claim the FP32 tree identity.
"""

import hashlib
from itertools import chain
from pathlib import Path

import torch

from heteroes.canonical import canonical_json_hash
from heteroes.eval import integer_cuda, integer_reference, reference_ops
from heteroes.eval.reference_ops import ReferenceArithmeticError
from heteroes.eval.strict_decoder import StrictDecoderReference
from heteroes.eval.strict_decoder_graph import StrictDecoderGraph, DEFAULT_GRAPH_BYTES

REFERENCE_BACKEND = "decoder_scaled_integer_reference_v1_experimental"
GRAPH_BACKEND = "decoder_scaled_integer_cuda_graph_v1_experimental"


def _compose(identity, backend, magnitude_bits):
    return {
        **identity,
        "backend": backend,
        "operators": {
            "linear": integer_reference.identity(magnitude_bits),
            "nonlinear": reference_ops.REFERENCE_OPS_VERSION,
        },
        "integerDecoderSourceSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "hardwareQualified": False,
    }


class IntegerDecoderReference(StrictDecoderReference):
    def __init__(self, model, *, magnitude_bits=22, max_context=256, allow_fixture=False):
        integer_reference._precision(magnitude_bits)
        if next(model.parameters()).device.type != "cpu":
            raise ReferenceArithmeticError("The independent integer decoder oracle is CPU-only")
        super().__init__(model, max_context=max_context, allow_fixture=allow_fixture)
        self.magnitude_bits = magnitude_bits
        self.identity = _compose(self.identity, REFERENCE_BACKEND, magnitude_bits)
        self.fingerprint = canonical_json_hash(self.identity)

    def _linear(self, value, module):
        return integer_reference.linear(
            value, module.weight, getattr(module, "bias", None), magnitude_bits=self.magnitude_bits
        )


class IntegerDecoderGraph(StrictDecoderGraph):
    def __init__(
        self,
        model,
        *,
        magnitude_bits=22,
        max_context=256,
        allow_fixture=False,
        max_graph_bytes=DEFAULT_GRAPH_BYTES,
        max_partial_bytes=16 * 1024**2,
    ):
        integer_reference._precision(magnitude_bits)
        super().__init__(model, max_context=max_context, allow_fixture=allow_fixture, max_graph_bytes=max_graph_bytes)
        self.kernels = integer_cuda.IntegerCudaKernels(
            self.device, magnitude_bits=magnitude_bits, max_partial_bytes=max_partial_bytes
        )
        self.identity = {
            **_compose(self.identity, GRAPH_BACKEND, magnitude_bits),
            "kernels": integer_cuda.static_identity(magnitude_bits, max_partial_bytes),
        }
        self.fingerprint = canonical_json_hash(self.identity)

    def _projection_weights(self):
        for layer in self.model.model.layers:
            for name in ("q_proj", "k_proj", "v_proj", "o_proj"):
                yield getattr(layer.self_attn, name).weight
            for name in ("gate_proj", "up_proj", "down_proj"):
                yield getattr(layer.mlp, name).weight
        yield self.model.lm_head.weight

    def _request_workspace_bytes(self):
        return sum(w.shape[0] * 4 for w in {id(w): w for w in self._projection_weights()}.values())

    def _generation_begin(self):
        self.kernels._begin_request(self._projection_weights())

    def _generation_end(self):
        self.kernels._end_request()
        # Also completes clearing after an error discarded the captured session, or on use_cache=False.
        torch.cuda.current_stream(self.device).synchronize()

    def buffers(self, *args, **kwargs):
        return chain(super().buffers(*args, **kwargs), self.kernels.weight_metadata_buffers())
