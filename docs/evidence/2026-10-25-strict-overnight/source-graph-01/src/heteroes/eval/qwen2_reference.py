"""Experimental Qwen2 graph over the explicit ADR-012 operation reference.

This wraps the live FP16 parameters; no model deepcopy, FP32 shadow or HF forward is used.
Prompts are packed and evaluated individually so padding/batch composition cannot shift reduction trees.
The eager implementation is an oracle/prototype, not a qualified or performant GPU backend.
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
from heteroes.eval.reference_ops import ReferenceArithmeticError

REFERENCE_BACKEND = "qwen2_pairwise_f32_reference_v1_experimental"


class Qwen2Reference:
    def __init__(self, model, *, max_context=256, allow_fixture=False):
        self.model = model
        self.config = config = model.config
        self.generation_config = model.generation_config
        self.device = next(model.parameters()).device
        if any(p.dtype != torch.float16 for p in model.parameters()):
            raise ReferenceArithmeticError("The reference uses live FP16 model parameters")
        if any(p.device != self.device for p in model.parameters()):
            raise ReferenceArithmeticError("One reference model must be on one device")
        if self.device.type == "cuda" and os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1":
            raise ReferenceArithmeticError("CUDA reference experiments need HETEROES_GPU_ACCEPTANCE=1")
        rope = getattr(config, "rope_parameters", None) or {
            "rope_theta": getattr(config, "rope_theta", 10000.0),
            "rope_type": "default",
        }
        self.theta = rope.get("rope_theta", 10000.0)
        if (
            type(model).__name__ != "Qwen2ForCausalLM"
            or config.model_type != "qwen2"
            or config.hidden_act != "silu"
            or rope.get("rope_type", "default") != "default"
            or set(rope) - {"rope_theta", "rope_type"}
            or getattr(config, "use_sliding_window", False)
            or any(kind != "full_attention" for kind in getattr(config, "layer_types", []))
            or model.training
            or not math.isfinite(self.theta)
            or self.theta <= 0
        ):
            raise ReferenceArithmeticError("Unsupported Qwen2 graph, RoPE or training configuration")
        signature = (
            config.hidden_size,
            config.intermediate_size,
            config.num_hidden_layers,
            config.num_attention_heads,
            config.num_key_value_heads,
            config.vocab_size,
            self.theta,
        )
        if not allow_fixture and signature != (896, 4864, 24, 14, 2, 151936, 1000000.0):
            raise ReferenceArithmeticError("Initial reference scope is the pinned Qwen2.5-0.5B configuration")
        self.head_dim = getattr(config, "head_dim", None) or config.hidden_size // config.num_attention_heads
        if (
            self.head_dim % 2
            or self.head_dim * config.num_attention_heads != config.hidden_size
            or config.num_attention_heads % config.num_key_value_heads
            or model.lm_head.weight is not model.model.embed_tokens.weight
        ):
            raise ReferenceArithmeticError("Unsupported attention dimensions or untied output head")
        if type(max_context) is not int or not 1 <= max_context <= min(config.max_position_embeddings, 32768):
            raise ReferenceArithmeticError("Invalid reference context limit")
        self.max_context = max_context
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
            "sourceSha256": hashlib.sha256(Path(__file__).read_bytes() + Path(ops.__file__).read_bytes()).hexdigest(),
            "modelSignature": list(signature),
            "rmsNormEpsilon": config.rms_norm_eps,
            "attentionScale": self._attention_scale,
            "ropeFrequencyBits": frequency_cpu.view(torch.int32).tolist(),
            "maxContext": max_context,
            "fixture": bool(allow_fixture),
            "hardwareQualified": False,
        }
        self.fingerprint = canonical_json_hash(self.identity)

    def parameters(self, *args, **kwargs):
        return self.model.parameters(*args, **kwargs)

    def buffers(self, *args, **kwargs):
        return chain(self.model.buffers(*args, **kwargs), (self._inverse_frequency,))

    @staticmethod
    def _linear(value, module):
        return ops.linear(value, module.weight, getattr(module, "bias", None))

    def _rotate(self, value, cosine, sine):
        half = self.head_dim // 2
        rotated = torch.cat((-value[..., half:], value[..., :half]), dim=-1)
        return ops.add(ops.mul(value, cosine), ops.mul(rotated, sine))

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
        return torch.cat(query_parts, dim=2).transpose(1, 2).reshape(1, query.shape[2], self.config.hidden_size)

    @torch.inference_mode()
    def forward_tokens(self, input_ids, cache=None):
        """Last-position logits and a call-local KV cache for ONE packed prompt.

        A cache may only be reused within a generation call, with unchanged live weights. Runtime generation never
        retains it across calls/candidates. Cache validation here is structural, not a parent-lineage certificate.
        """
        if (
            input_ids.dtype != torch.long
            or input_ids.ndim != 2
            or input_ids.shape[0] != 1
            or input_ids.shape[1] < 1
            or input_ids.device != self.device
            or bool(((input_ids < 0) | (input_ids >= self.config.vocab_size)).any())
        ):
            raise ReferenceArithmeticError("forward_tokens needs one nonempty packed token row")
        if cache is not None and len(cache) != self.config.num_hidden_layers:
            raise ReferenceArithmeticError("KV cache layer count mismatch")
        past = 0 if cache is None else cache[0][0].shape[2]
        length = input_ids.shape[1]
        if past + length > self.max_context:
            raise ReferenceArithmeticError("Reference context limit exceeded")
        if cache is not None:
            expected = (1, self.config.num_key_value_heads, past, self.head_dim)
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
        hidden = self.model.model.embed_tokens.weight[input_ids].float()
        positions = torch.arange(past, past + length, device=self.device, dtype=torch.float32)
        angles = ops.mul(positions[:, None], self._inverse_frequency[None, :])
        sine, cosine = ops.sin_cos(angles)
        sine, cosine = (torch.cat((part, part), dim=-1)[None, None, :, :] for part in (sine, cosine))
        new_cache = []
        for number, layer in enumerate(self.model.model.layers):
            residual = hidden
            normalized = ops.rms_norm(hidden, layer.input_layernorm.weight, self.config.rms_norm_eps)
            attention = layer.self_attn
            q = (
                self._linear(normalized, attention.q_proj)
                .reshape(1, length, self.config.num_attention_heads, self.head_dim)
                .transpose(1, 2)
            )
            k = (
                self._linear(normalized, attention.k_proj)
                .reshape(1, length, self.config.num_key_value_heads, self.head_dim)
                .transpose(1, 2)
            )
            v = (
                self._linear(normalized, attention.v_proj)
                .reshape(1, length, self.config.num_key_value_heads, self.head_dim)
                .transpose(1, 2)
            )
            q, k = self._rotate(q, cosine, sine), self._rotate(k, cosine, sine)
            if cache is not None:
                k, v = (torch.cat((old, current), dim=2) for old, current in zip(cache[number], (k, v)))
            new_cache.append((k, v))
            hidden = ops.add(residual, self._linear(self._attention(q, k, v, past), attention.o_proj))
            residual = hidden
            normalized = ops.rms_norm(hidden, layer.post_attention_layernorm.weight, self.config.rms_norm_eps)
            gated = ops.mul(
                ops.silu(self._linear(normalized, layer.mlp.gate_proj)), self._linear(normalized, layer.mlp.up_proj)
            )
            hidden = ops.add(residual, self._linear(gated, layer.mlp.down_proj))
        hidden = ops.rms_norm(hidden[:, -1], self.model.model.norm.weight, self.config.rms_norm_eps)
        return self._linear(hidden, self.model.lm_head), tuple(new_cache)

    @torch.inference_mode()
    def generate(
        self,
        input_ids,
        attention_mask=None,
        *,
        max_new_tokens=16,
        do_sample=False,
        use_cache=True,
        eos_token_id=None,
        pad_token_id=None,
        repetition_penalty=None,
        num_beams=1,
        num_return_sequences=1,
        **kwargs,
    ):
        if (
            kwargs
            or do_sample is not False
            or num_beams != 1
            or num_return_sequences != 1
            or type(use_cache) is not bool
        ):
            raise ReferenceArithmeticError("Only the declared plain greedy options are supported")
        if (
            input_ids.ndim != 2
            or input_ids.dtype != torch.long
            or input_ids.device != self.device
            or not input_ids.numel()
            or bool(((input_ids < 0) | (input_ids >= self.config.vocab_size)).any())
        ):
            raise ReferenceArithmeticError("Generation needs nonempty integer token rows on the model device")
        if type(max_new_tokens) is not int or max_new_tokens < 1:
            raise ReferenceArithmeticError("max_new_tokens must be a positive integer")
        mask = torch.ones_like(input_ids, dtype=torch.bool) if attention_mask is None else attention_mask
        if mask.shape != input_ids.shape or mask.device != self.device or bool(((mask != 0) & (mask != 1)).any()):
            raise ReferenceArithmeticError("Invalid attention mask")
        mask = mask.bool()
        eos = self.generation_config.eos_token_id if eos_token_id is None else eos_token_id
        end_tokens = [] if eos is None else [eos] if type(eos) is int else eos
        if not isinstance(end_tokens, (list, tuple)) or any(
            type(t) is not int or not 0 <= t < self.config.vocab_size for t in end_tokens
        ):
            raise ReferenceArithmeticError("Invalid EOS token ids")
        pad = self.generation_config.pad_token_id if pad_token_id is None else pad_token_id
        pad = end_tokens[0] if pad is None and end_tokens else pad
        if type(pad) is not int or not 0 <= pad < self.config.vocab_size:
            raise ReferenceArithmeticError("A valid padding token is required")
        penalty = self.generation_config.repetition_penalty if repetition_penalty is None else repetition_penalty
        penalty = 1.0 if penalty is None else penalty
        if (
            isinstance(penalty, bool)
            or not isinstance(penalty, (int, float))
            or not math.isfinite(penalty)
            or not 1e-30 <= penalty <= 1e30
        ):
            raise ReferenceArithmeticError("Invalid repetition penalty")
        prompts = []
        for row, allowed in zip(input_ids, mask):
            indices = allowed.nonzero().flatten()
            if not indices.numel() or not bool(allowed[indices[0] :].all()):
                raise ReferenceArithmeticError("The reference accepts nonempty left-padded prompts")
            prompt = row[indices][None, :]
            if prompt.shape[1] + max_new_tokens > self.max_context:
                raise ReferenceArithmeticError("Requested prompt/token budget exceeds the reference context limit")
            prompts.append(prompt)
        outputs = []
        for prompt in prompts:
            history, cache, generated = prompt, None, []
            for _ in range(max_new_tokens):
                current = history[:, -1:] if use_cache and cache is not None else history
                scores, new_cache = self.forward_tokens(current, cache if use_cache else None)
                cache = new_cache if use_cache else None
                if penalty != 1.0:
                    indices = history.unique()
                    selected = scores[0, indices]
                    inverse = ops.reciprocal(torch.tensor(penalty, dtype=torch.float32, device=self.device))
                    scores[0, indices] = torch.where(
                        selected < 0, ops.mul(selected, penalty), ops.mul(selected, inverse)
                    )
                # Integer min makes the lowest token id the explicit tie rule.
                maximum = scores.max()
                ids = torch.arange(self.config.vocab_size, device=self.device)
                token = torch.where(scores[0] == maximum, ids, self.config.vocab_size).amin().reshape(1, 1)
                generated.append(token)
                history = torch.cat((history, token), dim=1)
                if int(token.item()) in end_tokens:
                    break
            outputs.append(torch.cat(generated, dim=1)[0])
        completion = torch.full(
            (input_ids.shape[0], max(row.numel() for row in outputs)), pad, dtype=torch.long, device=self.device
        )
        for number, row in enumerate(outputs):
            completion[number, : row.numel()] = row
        return torch.cat((input_ids, completion), dim=1)
