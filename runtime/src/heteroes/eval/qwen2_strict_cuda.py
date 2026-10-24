"""Experimental Qwen2 graph executing the ADR-012 reference arithmetic with audited NVRTC kernels.

Same live FP16 weights, graph, cache format and generation rules as ``Qwen2Reference``; projections, RMSNorm,
residual adds, the SiLU gate, RoPE and attention run as kernels that are tested bit-for-bit against the eager
operations. RoPE tables, embeddings and the greedy/penalty step stay eager (once per forward/token).
Nonfinite or out-of-domain arithmetic is collected in one device flag and raised before logits are returned.
This is NOT a qualified backend: ``hardwareQualified`` stays false until hardware/OS/lifecycle gates pass.
"""

import os

import torch

from heteroes.canonical import canonical_json_hash
from heteroes.eval import reference_ops as ops
from heteroes.eval import strict_cuda
from heteroes.eval.qwen2_reference import Qwen2Reference
from heteroes.eval.reference_ops import ReferenceArithmeticError

STRICT_CUDA_BACKEND = "qwen2_pairwise_f32_cuda_v1_experimental"


class Qwen2StrictCuda(Qwen2Reference):
    def __init__(self, model, *, max_context=256, allow_fixture=False):
        if os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1":
            raise ReferenceArithmeticError("Strict CUDA backend experiments need HETEROES_GPU_ACCEPTANCE=1")
        if next(model.parameters()).device.type != "cuda":
            raise ReferenceArithmeticError("The strict CUDA backend needs the model on one CUDA device")
        super().__init__(model, max_context=max_context, allow_fixture=allow_fixture)
        if max_context > strict_cuda.MAX_ATTENTION_KEYS:
            raise ReferenceArithmeticError("Strict CUDA attention context limit exceeded")
        self.kernels = strict_cuda.StrictCudaKernels(self.device)
        self.identity = {
            **self.identity,
            "backend": STRICT_CUDA_BACKEND,
            "kernels": strict_cuda.static_identity(),
        }
        self.fingerprint = canonical_json_hash(self.identity)

    def kernel_identity(self):
        """Per-device build receipts (NVRTC, arch, binary hashes, audits); not part of the portable fingerprint."""
        return self.kernels.identity()

    def _project(self, value, module, flag):
        return self.kernels.linear(value, module.weight, getattr(module, "bias", None), error_flag=flag)

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
        positions = torch.arange(past, past + length, device=self.device, dtype=torch.float32)
        sine, cosine = ops.sin_cos(ops.mul(positions[:, None], self._inverse_frequency[None, :]))
        sine, cosine = (torch.cat((part, part), dim=-1).contiguous() for part in (sine, cosine))
        epsilon = float(config.rms_norm_eps)
        new_cache = []
        for number, layer in enumerate(self.model.model.layers):
            attention = layer.self_attn
            normalized = kernels.rms_norm(hidden, layer.input_layernorm.weight, epsilon, error_flag=flag)
            q = kernels.rope(self._project(normalized, attention.q_proj, flag), cosine, sine, heads, error_flag=flag)
            k = kernels.rope(self._project(normalized, attention.k_proj, flag), cosine, sine, kv_heads, error_flag=flag)
            v = self._project(normalized, attention.v_proj, flag).reshape(length, kv_heads, dim).transpose(0, 1)
            k, v = k[None], v[None].contiguous()
            if cache is not None:
                k, v = (torch.cat((old, current), dim=2) for old, current in zip(cache[number], (k, v)))
            new_cache.append((k, v))
            mixed = kernels.attention(
                q, k[0], v[0], past, heads // kv_heads, float(self._attention_scale), error_flag=flag
            )
            hidden = kernels.add(hidden, self._project(mixed, attention.o_proj, flag), error_flag=flag)
            normalized = kernels.rms_norm(hidden, layer.post_attention_layernorm.weight, epsilon, error_flag=flag)
            gated = kernels.silu_mul(
                self._project(normalized, layer.mlp.gate_proj, flag),
                self._project(normalized, layer.mlp.up_proj, flag),
                error_flag=flag,
            )
            hidden = kernels.add(hidden, self._project(gated, layer.mlp.down_proj, flag), error_flag=flag)
        final = kernels.rms_norm(hidden[-1:], self.model.model.norm.weight, epsilon, error_flag=flag)
        logits = self._project(final, self.model.lm_head, flag)
        kernels.raise_if_error(flag)
        return logits, tuple(new_cache)
