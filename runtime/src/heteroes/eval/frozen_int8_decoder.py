"""Experimental decoder composition over typed frozen-int8 projections and FP16 LoRA adapters.

The base projections keep the pinned int8 artifact and execute the exact B22 three-limb product; only the
adapter factors are trainable and their delta uses its own FP32 namespace. Embeddings, normalization weights and
a tied or untied FP16 LM head keep the existing strict graph arithmetic. This module composes existing pieces; it
does not change a managed recipe, qualify hardware or claim the FP32-tree identity.
"""

import hashlib
from pathlib import Path

from heteroes.canonical import canonical_json_hash
from heteroes.eval import frozen_int8 as artifact
from heteroes.eval import frozen_int8_cuda
from heteroes.eval import integer_plan
from heteroes.eval import reference_ops
from heteroes.eval.reference_ops import ReferenceArithmeticError
from heteroes.eval.strict_decoder import StrictDecoderReference
from heteroes.eval.strict_decoder_graph import DEFAULT_GRAPH_BYTES, StrictDecoderGraph

REFERENCE_BACKEND = "decoder_frozen_int8_lora_reference_v1_experimental"
GRAPH_BACKEND = "decoder_frozen_int8_lora_cuda_graph_v1_experimental"


def _compose(identity, backend):
    return {
        **identity,
        "backend": backend,
        "operators": {
            "linear": artifact.identity(),
            "nonlinear": reference_ops.REFERENCE_OPS_VERSION,
        },
        "adapterStorage": artifact.ADAPTER_STORAGE_VERSION,
        "adapterArithmetic": artifact.ADAPTER_ARITHMETIC_VERSION,
        "frozenDecoderSourceSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "hardwareQualified": False,
    }


def _is_frozen(module):
    return bool(getattr(module, "is_frozen_int8_linear", False))


class FrozenInt8DecoderReference(StrictDecoderReference):
    """CPU eager oracle for the frozen-int8 base plus separately named adapter arithmetic."""

    def __init__(self, model, *, max_context=256, allow_fixture=False):
        if next(model.parameters()).device.type != "cpu":
            raise ReferenceArithmeticError("The frozen int8 decoder oracle is CPU-only")
        super().__init__(model, max_context=max_context, allow_fixture=allow_fixture, frozen_int8=True)
        self.identity = _compose(self.identity, REFERENCE_BACKEND)
        self.fingerprint = canonical_json_hash(self.identity)

    def _linear(self, value, module):
        if _is_frozen(module):
            return module(value)
        return super()._linear(value, module)


class FrozenInt8DecoderGraph(StrictDecoderGraph):
    """Captured decode over typed frozen projections; only projection dispatch differs from the strict graph."""

    def __init__(
        self,
        model,
        *,
        max_context=256,
        allow_fixture=False,
        max_graph_bytes=DEFAULT_GRAPH_BYTES,
        max_partial_bytes=16 * 1024**2,
        decode_target_ctas_per_sm=8,
    ):
        try:
            integer_plan.validate_target(decode_target_ctas_per_sm)
        except ValueError as error:
            raise ReferenceArithmeticError(str(error)) from error
        super().__init__(
            model,
            max_context=max_context,
            allow_fixture=allow_fixture,
            max_graph_bytes=max_graph_bytes,
            frozen_int8=True,
        )
        self.frozen_kernels = frozen_int8_cuda.FrozenInt8CudaKernels(self.device, max_partial_bytes=max_partial_bytes)
        self._decode_target = decode_target_ctas_per_sm
        self._workspace_bounds = {}
        self._kernel_configuration = self._current_kernel_configuration()
        self._frozen = tuple(self.model.get_submodule(name) for name in self.identity["graph"]["frozenProjections"])
        self.identity = {
            **_compose(self.identity, GRAPH_BACKEND),
            "frozenKernels": frozen_int8_cuda.static_identity(max_partial_bytes),
            "decodeExecution": {
                **integer_plan.identity(),
                "targetCtasPerSm": decode_target_ctas_per_sm,
            },
        }
        self.fingerprint = canonical_json_hash(self.identity)

    @property
    def decode_target_ctas_per_sm(self):
        return self._decode_target

    def kernel_identity(self):
        """Per-device build receipts for the strict and frozen operators."""
        return {"strict": super().kernel_identity(), "frozen": self.frozen_kernels.identity()}

    def _current_kernel_configuration(self):
        return tuple(
            getattr(self.frozen_kernels, name, None)
            for name in ("magnitude_bits", "max_partial_bytes", "device", "multiprocessors")
        )

    def _check_kernel_configuration(self):
        if self._current_kernel_configuration() != self._kernel_configuration:
            raise ReferenceArithmeticError("Frozen int8 graph execution configuration changed; construct a new backend")

    def _frozen_bases(self, value, modules, flag):
        return self.frozen_kernels.linear_many(
            value,
            tuple((module.weight_q, module.weight_scale) for module in modules),
            tuple(getattr(module, "bias", None) for module in modules),
            error_flag=flag,
        )

    def _project(self, value, module, flag):
        if not _is_frozen(module):
            return super()._project(value, module, flag)
        base = self.frozen_kernels.linear(
            value,
            module.weight_q,
            module.weight_scale,
            getattr(module, "bias", None),
            error_flag=flag,
        )
        return artifact.combine_adapter(base, module.lora_delta(value))

    def _project_many(self, value, modules, flag):
        modules = tuple(modules)
        if modules and all(_is_frozen(module) for module in modules):
            bases = self._frozen_bases(value, modules, flag)
            return tuple(
                artifact.combine_adapter(base, module.lora_delta(value))
                for base, module in zip(bases, modules, strict=True)
            )
        return tuple(self._project(value, module, flag) for module in modules)

    def _decode_project(self, value, module, flag):
        if not _is_frozen(module):
            return super()._decode_project(value, module, flag)
        base = self.frozen_kernels.linear_decode(
            value,
            module.weight_q,
            module.weight_scale,
            getattr(module, "bias", None),
            error_flag=flag,
            target_ctas_per_sm=self._decode_target,
        )
        return artifact.combine_adapter(base, module.lora_delta(value))

    def _decode_project_many(self, value, modules, flag):
        modules = tuple(modules)
        if modules and all(_is_frozen(module) for module in modules):
            bases = self.frozen_kernels.linear_many(
                value,
                tuple((module.weight_q, module.weight_scale) for module in modules),
                tuple(getattr(module, "bias", None) for module in modules),
                error_flag=flag,
                decode_target_ctas_per_sm=self._decode_target,
            )
            return tuple(
                artifact.combine_adapter(base, module.lora_delta(value))
                for base, module in zip(bases, modules, strict=True)
            )
        return tuple(self._decode_project(value, module, flag) for module in modules)

    def _request_workspace_bytes(self, capacity=1):
        self._check_kernel_configuration()
        shapes = tuple((module.in_features, module.out_features) for module in self._frozen)
        key = (capacity, shapes)
        if key not in self._workspace_bounds:
            self._workspace_bounds[key] = integer_plan.decode_workspace_bound(
                shapes,
                capacity,
                self.frozen_kernels.multiprocessors,
                max_partial_bytes=self.frozen_kernels.max_partial_bytes,
                target_ctas_per_sm=self._decode_target,
            )
        # Packed input replaces the FP32-sized activation term already covered by graph_memory_bound.
        padding = (
            capacity
            * self.max_context
            * sum(max(0, artifact.ACTIVATION_LIMBS * 4 * ((width + 3) // 4) - 4 * width) for width, _ in shapes)
        )
        return self._workspace_bounds[key] + padding
