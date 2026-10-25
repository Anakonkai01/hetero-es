"""Model-independent strict decoder graph and explicit architectural capability checks.

Supported graph: dense causal GQA, default full-dimension RoPE, RMSNorm, SiLU-gated MLP, FP16 projections
with optional bias, and tied or untied LM heads. Qwen2, Llama and Mistral are validated adapters to this graph,
not hardware qualifications. Unknown families, sliding attention, scaled RoPE and unconsumed weights fail.
"""

from decimal import Decimal, localcontext
import hashlib
from itertools import chain
import math
import os
from pathlib import Path

import torch

from heteroes.canonical import canonical_json_hash
from heteroes.eval import reference_ops as ops
from heteroes.eval import qwen2_reference as reference_graph
from heteroes.eval import strict_cuda
from heteroes.eval.qwen2_reference import Qwen2Reference
from heteroes.eval.reference_ops import ReferenceArithmeticError

GRAPH_VERSION = "rms_swiglu_causal_rope_decoder_v1_experimental"
REFERENCE_BACKEND = "decoder_pairwise_f32_reference_v1_experimental"
CUDA_BACKEND = "decoder_pairwise_f32_cuda_v1_experimental"
FAMILIES = {"qwen2": "Qwen2ForCausalLM", "llama": "LlamaForCausalLM", "mistral": "MistralForCausalLM"}


def describe_graph(model, max_context, *, frozen_int8=False):
    if type(frozen_int8) is not bool:
        raise ReferenceArithmeticError("The frozen-int8 graph mode must be a boolean")
    config = model.config
    family = config.model_type
    rope = getattr(config, "rope_parameters", None) or {
        "rope_theta": getattr(config, "rope_theta", 10000.0),
        "rope_type": "default",
    }
    theta = rope.get("rope_theta", 10000.0)
    dimensions = (
        config.hidden_size,
        config.intermediate_size,
        config.num_hidden_layers,
        config.num_attention_heads,
        config.num_key_value_heads,
        config.vocab_size,
    )
    if (
        FAMILIES.get(family) != type(model).__name__
        or model.training
        or config.hidden_act != "silu"
        or rope.get("rope_type", "default") != "default"
        or set(rope) - {"rope_theta", "rope_type"}
        or not isinstance(theta, (int, float))
        or not math.isfinite(theta)
        or theta <= 0
        or getattr(config, "sliding_window", None) is not None
        or getattr(config, "use_sliding_window", False)
        or any(kind != "full_attention" for kind in (getattr(config, "layer_types", None) or []))
        or any(type(n) is not int or n < 1 for n in dimensions)
    ):
        raise ReferenceArithmeticError("Unsupported graph family, attention, RoPE or activation")
    hidden, intermediate, layers, heads, kv_heads, vocab = dimensions
    dim = getattr(config, "head_dim", None) or hidden // heads
    epsilon = config.rms_norm_eps
    if (
        type(dim) is not int
        or dim < 2
        or dim % 2
        or dim > 256
        or heads % kv_heads
        or heads * dim > strict_cuda.MAX_LINEAR_WIDTH
        or hidden > strict_cuda.MAX_NORM_WIDTH
        or intermediate > strict_cuda.MAX_LINEAR_WIDTH
        or not isinstance(epsilon, (int, float))
        or not math.isfinite(epsilon)
        or epsilon <= 0
        or type(max_context) is not int
        or not 1 <= max_context <= min(config.max_position_embeddings, strict_cuda.MAX_ATTENTION_KEYS)
        or len(model.model.layers) != layers
    ):
        raise ReferenceArithmeticError("Unsupported graph dimensions, norm or context")
    device = next(model.parameters()).device
    parameters = dict(model.named_parameters(remove_duplicate=False))
    if any(p.dtype != torch.float16 or p.device != device for p in parameters.values()):
        raise ReferenceArithmeticError("Graph needs one live FP16 weight set on one device")
    expected = {}
    frozen = {}

    def frozen_projection(name, module, outputs, inputs):
        weight_q = getattr(module, "weight_q", None)
        weight_scale = getattr(module, "weight_scale", None)
        if (
            not isinstance(weight_q, torch.Tensor)
            or weight_q.dtype != torch.int8
            or tuple(weight_q.shape) != (outputs, inputs)
            or weight_q.device != device
            or not weight_q.is_contiguous()
            or not isinstance(weight_scale, torch.Tensor)
            or weight_scale.dtype != torch.float32
            or tuple(weight_scale.shape) != (outputs,)
            or weight_scale.device != device
            or not weight_scale.is_contiguous()
            or hasattr(module, "weight")
            or getattr(module, "in_features", None) != inputs
            or getattr(module, "out_features", None) != outputs
            or getattr(module, "training", True)
        ):
            raise ReferenceArithmeticError(f"Unsupported frozen int8 projection storage at {name}")
        digest = getattr(module, "artifact_sha256", None)
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ReferenceArithmeticError(f"Frozen int8 projection {name} lacks a pinned artifact digest")
        rank = getattr(module, "rank", None)
        alpha = getattr(module, "alpha", None)
        scaling = getattr(module, "scaling", None)
        if (
            type(rank) is not int
            or rank < 1
            or isinstance(alpha, bool)
            or not isinstance(alpha, (int, float))
            or not math.isfinite(alpha)
            or alpha <= 0
            or scaling != float(alpha) / rank
        ):
            raise ReferenceArithmeticError(f"Frozen int8 projection {name} has an invalid LoRA configuration")
        adapter = getattr(module, "adapter_name", None)
        first = getattr(module, "lora_A", None)
        second = getattr(module, "lora_B", None)
        if (
            not isinstance(adapter, str)
            or not adapter
            or "." in adapter
            or not isinstance(first, torch.nn.ModuleDict)
            or not isinstance(second, torch.nn.ModuleDict)
            or set(first.keys()) != {adapter}
            or set(second.keys()) != {adapter}
        ):
            raise ReferenceArithmeticError(f"Frozen int8 projection {name} has an unsupported adapter set")
        for label, child, shape in (("A", first[adapter], (rank, inputs)), ("B", second[adapter], (outputs, rank))):
            weight = getattr(child, "weight", None)
            if (
                not isinstance(weight, torch.Tensor)
                or weight.dtype != torch.float16
                or tuple(weight.shape) != shape
                or weight.device != device
                or not weight.is_contiguous()
                or not weight.requires_grad
            ):
                raise ReferenceArithmeticError(f"Frozen int8 projection {name} has an invalid LoRA {label} factor")
            expected[f"{name}.lora_{label}.{adapter}.weight"] = shape
        bias = getattr(module, "bias", None)
        if bias is not None and (
            not isinstance(bias, torch.Tensor)
            or bias.dtype != torch.float16
            or tuple(bias.shape) != (outputs,)
            or bias.device != device
            or not bias.is_contiguous()
        ):
            raise ReferenceArithmeticError(f"Frozen int8 projection {name} has an invalid frozen bias")
        frozen[name] = {
            "artifactSha256": digest,
            "rank": rank,
            "alpha": float(alpha),
            "scaling": scaling,
            "inFeatures": inputs,
            "outFeatures": outputs,
            "bias": bias is not None,
        }

    def projection(name, module, outputs, inputs):
        if getattr(module, "is_frozen_int8_linear", False):
            if not frozen_int8:
                raise ReferenceArithmeticError("Frozen int8 projections need the explicit frozen graph mode")
            frozen_projection(name, module, outputs, inputs)
            return
        expected[name + ".weight"] = (outputs, inputs)
        if getattr(module, "bias", None) is not None:
            expected[name + ".bias"] = (outputs,)

    def norm(name, module):
        expected[name + ".weight"] = (hidden,)
        if getattr(module, "variance_epsilon", None) != epsilon:
            raise ReferenceArithmeticError("Unsupported graph RMSNorm epsilon")

    expected["model.embed_tokens.weight"] = (vocab, hidden)
    projection("lm_head", model.lm_head, vocab, hidden)
    norm("model.norm", model.model.norm)
    for i, layer in enumerate(model.model.layers):
        prefix = f"model.layers.{i}"
        norm(prefix + ".input_layernorm", layer.input_layernorm)
        norm(prefix + ".post_attention_layernorm", layer.post_attention_layernorm)
        for name, outputs, inputs in (
            ("q_proj", heads * dim, hidden),
            ("k_proj", kv_heads * dim, hidden),
            ("v_proj", kv_heads * dim, hidden),
            ("o_proj", hidden, heads * dim),
        ):
            projection(prefix + ".self_attn." + name, getattr(layer.self_attn, name), outputs, inputs)
        for name, outputs, inputs in (
            ("gate_proj", intermediate, hidden),
            ("up_proj", intermediate, hidden),
            ("down_proj", hidden, intermediate),
        ):
            projection(prefix + ".mlp." + name, getattr(layer.mlp, name), outputs, inputs)
    if set(parameters) != set(expected) or any(
        tuple(parameters[name].shape) != shape for name, shape in expected.items()
    ):
        raise ReferenceArithmeticError("Unsupported graph parameters: missing, unconsumed or incompatible weights")
    tied_weight = getattr(model.lm_head, "weight", None)
    tied = tied_weight is not None and tied_weight is model.model.embed_tokens.weight
    if tied != bool(config.tie_word_embeddings):
        raise ReferenceArithmeticError("Unsupported graph tied-head metadata mismatch")
    if frozen_int8 and not frozen:
        raise ReferenceArithmeticError("The explicit frozen int8 graph mode selects no typed projection")
    result = {
        "version": GRAPH_VERSION,
        "family": family,
        "dimensions": list(dimensions),
        "headDim": dim,
        "ropeTheta": theta,
        "rmsNormEpsilon": epsilon,
        "tiedHead": tied,
        "parameterShapes": {name: list(shape) for name, shape in sorted(expected.items())},
    }
    if frozen_int8:
        result["frozenProjections"] = dict(sorted(frozen.items()))
    return result


class StrictDecoderReference(Qwen2Reference):
    """Independent eager operator oracle for every admitted graph adapter, with no vendor forward call."""

    def __init__(self, model, *, max_context=256, allow_fixture=False, frozen_int8=False):
        if next(model.parameters()).device.type == "cuda" and os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1":
            raise ReferenceArithmeticError("CUDA reference experiments need HETEROES_GPU_ACCEPTANCE=1")
        graph = describe_graph(model, max_context, frozen_int8=frozen_int8)
        self.model, self.config, self.generation_config = model, model.config, model.generation_config
        self.frozen_int8 = frozen_int8
        self.device = next(model.parameters()).device
        self.head_dim, self.theta, self.max_context = graph["headDim"], graph["ropeTheta"], max_context
        with localcontext() as context:
            context.prec = 80
            theta = Decimal(str(self.theta))
            frequencies = [float(theta ** (-Decimal(i) / Decimal(self.head_dim))) for i in range(0, self.head_dim, 2)]
            self._attention_scale = float(Decimal(self.head_dim).sqrt() ** -1)
        frequency_cpu = torch.tensor(frequencies, dtype=torch.float32)
        self._inverse_frequency = frequency_cpu.to(self.device)
        self.identity = {
            "backend": REFERENCE_BACKEND,
            "operators": ops.REFERENCE_OPS_VERSION,
            "graph": graph,
            "sourceSha256": hashlib.sha256(
                Path(__file__).read_bytes()
                + Path(ops.__file__).read_bytes()
                + Path(reference_graph.__file__).read_bytes()
            ).hexdigest(),
            "attentionScale": self._attention_scale,
            "ropeFrequencyBits": frequency_cpu.view(torch.int32).tolist(),
            "maxContext": max_context,
            "fixture": bool(allow_fixture),
            "hardwareQualified": False,
        }
        self.fingerprint = canonical_json_hash(self.identity)

    def _linear(self, value, module):
        """Projection hook for adapters that replace the FP16 linear contract."""
        if getattr(module, "is_frozen_int8_linear", False):
            raise ReferenceArithmeticError("This reference has no frozen int8 projection arithmetic")
        return super()._linear(value, module)

    def _attention(self, query, key, value, past_length):
        repeats = self.config.num_attention_heads // self.config.num_key_value_heads
        key = key.repeat_interleave(repeats, dim=1)
        value = value.repeat_interleave(repeats, dim=1)
        scale = self._attention_scale
        keys = key.shape[2]
        query_parts = []
        for start in range(0, query.shape[2], 4):
            q = query[:, :, start : start + 4]
            score_parts = []
            for k in range(0, keys, 32):
                products = ops.mul(q[:, :, :, None, :], key[:, :, None, k : k + 32, :])
                score_parts.append(ops.mul(ops.pairwise_sum(products), scale))
            scores = torch.cat(score_parts, dim=-1)
            positions = torch.arange(past_length + start, past_length + start + q.shape[2], device=query.device)
            causal = torch.arange(keys, device=query.device)[None, None, None, :] <= positions[None, None, :, None]
            probabilities = ops.softmax(scores, causal)
            channels = []
            for d in range(0, self.head_dim, 16):
                v = value[:, :, :, d : d + 16].transpose(-1, -2)
                channels.append(ops.pairwise_sum(ops.mul(probabilities[:, :, :, None, :], v[:, :, None, :, :])))
            query_parts.append(torch.cat(channels, dim=-1))
        return (
            torch.cat(query_parts, dim=2)
            .transpose(1, 2)
            .reshape(1, query.shape[2], self.config.num_attention_heads * self.head_dim)
        )


def require_cuda(model):
    if os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1":
        raise ReferenceArithmeticError("Strict CUDA backend experiments need HETEROES_GPU_ACCEPTANCE=1")
    if next(model.parameters()).device.type != "cuda":
        raise ReferenceArithmeticError("The strict CUDA backend needs the model on one CUDA device")


class CudaDecoderMixin:
    def _initialize_cuda_graph(self, backend):
        self.kernels = strict_cuda.StrictCudaKernels(self.device)
        with torch.inference_mode():
            positions = torch.arange(self.max_context, device=self.device, dtype=torch.float32)
            sine, cosine = ops.sin_cos(ops.mul(positions[:, None], self._inverse_frequency[None, :]))
            self._rope_sine, self._rope_cosine = (
                torch.cat((part, part), dim=-1).contiguous() for part in (sine, cosine)
            )
        self.identity = {
            **self.identity,
            "backend": backend,
            "graphSourceSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "kernels": strict_cuda.static_identity(),
        }
        self.fingerprint = canonical_json_hash(self.identity)

    def buffers(self, *args, **kwargs):
        return chain(super().buffers(*args, **kwargs), (self._rope_sine, self._rope_cosine))

    def kernel_identity(self):
        """Per-device build receipts (NVRTC, arch, binary hashes, audits); not part of the portable fingerprint."""
        return self.kernels.identity()

    def _project(self, value, module, flag):
        return self.kernels.linear(value, module.weight, getattr(module, "bias", None), error_flag=flag)

    def _project_many(self, value, modules, flag):
        return tuple(self._project(value, module, flag) for module in modules)

    @torch.inference_mode()
    def forward_tokens(self, input_ids, cache=None):
        """Last-position logits and a call-local KV cache for ONE packed prompt, in the reference cache format."""
        config, kernels = self.config, self.kernels
        if (
            input_ids.dtype != torch.long
            or input_ids.ndim != 2
            or input_ids.shape[0] != 1
            or input_ids.shape[1] < 1
            or input_ids.device != self.device
            or bool(((input_ids < 0) | (input_ids >= config.vocab_size)).any())
        ):
            raise ReferenceArithmeticError("forward_tokens needs one nonempty packed token row")
        if cache is not None and len(cache) != config.num_hidden_layers:
            raise ReferenceArithmeticError("KV cache layer count mismatch")
        past = 0 if cache is None else cache[0][0].shape[2]
        length = input_ids.shape[1]
        if past + length > self.max_context:
            raise ReferenceArithmeticError("Reference context limit exceeded")
        heads, kv_heads, dim = config.num_attention_heads, config.num_key_value_heads, self.head_dim
        if cache is not None:
            expected = (1, kv_heads, past, dim)
            if any(
                k.shape != expected
                or v.shape != expected
                or k.dtype != torch.float32
                or v.dtype != torch.float32
                or k.device != self.device
                or v.device != self.device
                for k, v in cache
            ):
                raise ReferenceArithmeticError("KV cache shape/dtype/device mismatch")
        flag = kernels.new_error_flag()
        hidden = self.model.model.embed_tokens.weight[input_ids[0]].float()
        sine, cosine = self._rope_sine[past : past + length], self._rope_cosine[past : past + length]
        epsilon = float(config.rms_norm_eps)
        new_cache = []
        for number, layer in enumerate(self.model.model.layers):
            attention = layer.self_attn
            normalized = kernels.rms_norm(hidden, layer.input_layernorm.weight, epsilon, error_flag=flag)
            q, k, v = self._project_many(normalized, (attention.q_proj, attention.k_proj, attention.v_proj), flag)
            q = kernels.rope(q, cosine, sine, heads, error_flag=flag)
            k = kernels.rope(k, cosine, sine, kv_heads, error_flag=flag)
            v = v.reshape(length, kv_heads, dim).transpose(0, 1)
            k, v = k[None], v[None].contiguous()
            if cache is not None:
                k, v = (torch.cat((old, current), dim=2) for old, current in zip(cache[number], (k, v)))
            new_cache.append((k, v))
            mixed = kernels.attention(
                q, k[0], v[0], past, heads // kv_heads, float(self._attention_scale), error_flag=flag
            )
            hidden = kernels.add(hidden, self._project(mixed, attention.o_proj, flag), error_flag=flag)
            normalized = kernels.rms_norm(hidden, layer.post_attention_layernorm.weight, epsilon, error_flag=flag)
            gate, up = self._project_many(normalized, (layer.mlp.gate_proj, layer.mlp.up_proj), flag)
            gated = kernels.silu_mul(gate, up, error_flag=flag)
            hidden = kernels.add(hidden, self._project(gated, layer.mlp.down_proj, flag), error_flag=flag)
        final = kernels.rms_norm(hidden[-1:], self.model.model.norm.weight, epsilon, error_flag=flag)
        logits = self._project(final, self.model.lm_head, flag)
        kernels.raise_if_error(flag)
        return logits, tuple(new_cache)


class StrictDecoderCuda(CudaDecoderMixin, StrictDecoderReference):
    def __init__(self, model, *, max_context=256, allow_fixture=False, frozen_int8=False):
        require_cuda(model)
        super().__init__(model, max_context=max_context, allow_fixture=allow_fixture, frozen_int8=frozen_int8)
        self._initialize_cuda_graph(CUDA_BACKEND)
