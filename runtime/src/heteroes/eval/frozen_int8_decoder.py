"""Experimental decoder composition over typed frozen-int8 projections and FP16 LoRA adapters.

The base projections keep the pinned int8 artifact and execute the exact B22 three-limb product; only the
adapter factors are trainable and their delta uses its own FP32 namespace. Embeddings and normalization weights
keep the strict graph arithmetic. A tied FP16 LM head can stay on the strict path or carry optional sidecar int8
storage prepared by ``freeze_tied_head``; the sidecar preserves the embedding tie and moves only the head
projection onto the pinned product. This module composes existing pieces; it does not change a managed recipe,
qualify hardware or claim the FP32-tree identity.
"""

import hashlib
from pathlib import Path

import torch

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


def _is_frozen_head(module):
    return bool(getattr(module, "is_frozen_int8_head", False))


class FrozenInt8DecoderReference(StrictDecoderReference):
    """CPU eager oracle for the frozen-int8 base plus separately named adapter arithmetic."""

    def __init__(self, model, *, max_context=256, allow_fixture=False):
        if next(model.parameters()).device.type != "cpu":
            raise ReferenceArithmeticError("The frozen int8 decoder oracle is CPU-only")
        super().__init__(model, max_context=max_context, allow_fixture=allow_fixture, frozen_int8=True)
        self._head_artifact = self._tied_head_artifact()
        self.identity = _compose(self.identity, REFERENCE_BACKEND)
        self.fingerprint = canonical_json_hash(self.identity)

    def _tied_head_artifact(self):
        head = self.model.lm_head
        if not _is_frozen_head(head):
            return None
        return artifact.FrozenInt8Artifact(
            weight_q=head.frozen_weight_q,
            weight_scale=head.frozen_weight_scale,
            metadata=dict(head.frozen_head_metadata),
            sha256=head.frozen_head_sha256,
            format_version=artifact.ARTIFACT_FORMAT_VERSION,
        )

    def _linear(self, value, module):
        if _is_frozen(module):
            return module(value)
        if module is self.model.lm_head and self._head_artifact is not None:
            return artifact.linear(value, self._head_artifact, getattr(module, "bias", None))
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
        for name, module in model.named_modules():
            if _is_frozen(module) and type(getattr(module, "rank", None)) is int and module.rank > 32:
                raise ReferenceArithmeticError(f"Frozen CUDA projection {name} requires LoRA rank <= 32")
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
        self._frozen_head = self.model.lm_head if "frozenTiedHead" in self.identity["graph"] else None
        self._frozen_seal = None
        self._verify_frozen_storage()
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

    def _frozen_storage_state(self):
        state = []
        for module in self._frozen:
            state.append(
                (
                    id(module.weight_q),
                    module.weight_q.data_ptr(),
                    module.weight_q._version,
                    id(module.weight_scale),
                    module.weight_scale.data_ptr(),
                    module.weight_scale._version,
                    canonical_json_hash(module.artifact_metadata),
                )
            )
        head = self._frozen_head
        if head is not None:
            state.append(
                (
                    id(head.frozen_weight_q),
                    head.frozen_weight_q.data_ptr(),
                    head.frozen_weight_q._version,
                    id(head.frozen_weight_scale),
                    head.frozen_weight_scale.data_ptr(),
                    head.frozen_weight_scale._version,
                    canonical_json_hash(head.frozen_head_metadata),
                )
            )
        return tuple(state)

    def _verify_frozen_storage(self):
        """Re-hash only when a frozen tensor object, pointer or version changed.

        The seal is checked at engine construction and at each generation request boundary, never per decode
        token. Replacement with an identical payload is admitted as a new capture; an in-place edit raises.
        """
        state = self._frozen_storage_state()
        if state == self._frozen_seal:
            return
        with torch.inference_mode():
            for module in self._frozen:
                artifact.verify_payload(
                    module.weight_q, module.weight_scale, module.artifact_metadata, module.artifact_sha256
                )
            head = self._frozen_head
            if head is not None:
                artifact.verify_payload(
                    head.frozen_weight_q,
                    head.frozen_weight_scale,
                    head.frozen_head_metadata,
                    head.frozen_head_sha256,
                )
        self._frozen_seal = state

    def _session_for(self, capacity):
        self._verify_frozen_storage()
        return super()._session_for(capacity)

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

    def _adapter_middle(self, value, module, flag):
        """First strict rank product. One row per block; the row tree itself is unchanged."""
        return self.kernels.linear(
            value,
            module.lora_A[module.adapter_name].weight,
            None,
            error_flag=flag,
            row_tile=1,
        )

    def _adapter_finish(self, middle, base, module, flag):
        """Keep the strict tree; schedule short rank products independently along the output dimension."""
        return self.kernels.lora_finish(
            middle,
            module.lora_B[module.adapter_name].weight,
            base,
            module.scaling,
            error_flag=flag,
            execution="output" if module.rank <= 16 else "warp",
        )

    def _project(self, value, module, flag):
        if module is self._frozen_head:
            return self.frozen_kernels.linear(
                value,
                module.frozen_weight_q,
                module.frozen_weight_scale,
                getattr(module, "bias", None),
                error_flag=flag,
            )
        if not _is_frozen(module):
            return super()._project(value, module, flag)
        base = self.frozen_kernels.linear(
            value,
            module.weight_q,
            module.weight_scale,
            getattr(module, "bias", None),
            error_flag=flag,
        )
        return self._adapter_finish(self._adapter_middle(value, module, flag), base, module, flag)

    def _project_many(self, value, modules, flag):
        modules = tuple(modules)
        if modules and all(_is_frozen(module) for module in modules):
            bases = self._frozen_bases(value, modules, flag)
            return tuple(
                self._adapter_finish(self._adapter_middle(value, module, flag), base, module, flag)
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
        return self._adapter_finish(self._adapter_middle(value, module, flag), base, module, flag)

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
                self._adapter_finish(self._adapter_middle(value, module, flag), base, module, flag)
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
