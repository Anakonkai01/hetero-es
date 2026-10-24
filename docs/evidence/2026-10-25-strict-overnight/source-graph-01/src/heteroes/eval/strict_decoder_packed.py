"""Experimental packed decoder execution with the strict arithmetic and one live FP16 weight set.

Variable-length sequences share projections, normalization, RoPE and an attention launch. Their KV ranges,
absolute positions, causal masks and reduction trees remain independent. Generation compacts finished rows;
caches are local to one call and never reused across candidate mutation. This is not a managed/qualified backend.
"""

import hashlib
import math
from pathlib import Path

import torch

from heteroes.canonical import canonical_json_hash
from heteroes.eval import reference_ops as ops
from heteroes.eval.strict_decoder import StrictDecoderCuda
from heteroes.eval.reference_ops import ReferenceArithmeticError

STRICT_PACKED_BACKEND = "decoder_pairwise_f32_cuda_packed_v1_experimental"
MAX_BATCH = 128


class StrictDecoderPacked(StrictDecoderCuda):
    def __init__(self, model, *, max_context=256, allow_fixture=False):
        super().__init__(model, max_context=max_context, allow_fixture=allow_fixture)
        self.identity = {
            **self.identity,
            "backend": STRICT_PACKED_BACKEND,
            "packedSourceSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "maxBatch": MAX_BATCH,
        }
        self.fingerprint = canonical_json_hash(self.identity)

    def _batch_layout(self, rows, caches):
        if not isinstance(rows, (list, tuple)) or not 1 <= len(rows) <= MAX_BATCH:
            raise ReferenceArithmeticError("Packed forward needs 1..128 nonempty token rows")
        if not isinstance(caches, (list, tuple)) or len(caches) != len(rows):
            raise ReferenceArithmeticError("Packed cache count mismatch")
        lengths, pasts = [], []
        for row, cache in zip(rows, caches):
            if (
                not isinstance(row, torch.Tensor)
                or row.dtype != torch.long
                or row.ndim != 2
                or row.shape[0] != 1
                or row.shape[1] < 1
                or row.device != self.device
            ):
                raise ReferenceArithmeticError("Packed forward needs nonempty integer token rows on its device")
            past = 0
            if cache is not None:
                if not isinstance(cache, (list, tuple)) or len(cache) != self.config.num_hidden_layers:
                    raise ReferenceArithmeticError("Packed KV cache layer count mismatch")
                for pair in cache:
                    if (
                        not isinstance(pair, (list, tuple))
                        or len(pair) != 2
                        or any(
                            not isinstance(t, torch.Tensor)
                            or t.ndim != 4
                            or t.shape[:2] != (1, self.config.num_key_value_heads)
                            or t.shape[-1] != self.head_dim
                            or t.dtype != torch.float32
                            or t.device != self.device
                            for t in pair
                        )
                    ):
                        raise ReferenceArithmeticError("Packed KV cache shape/dtype/device mismatch")
                past = cache[0][0].shape[2]
                if any(k.shape[2] != past or v.shape[2] != past for k, v in cache):
                    raise ReferenceArithmeticError("Packed KV cache prefix lengths disagree")
            length = row.shape[1]
            if past + length > self.max_context:
                raise ReferenceArithmeticError("Packed context limit exceeded")
            lengths.append(length)
            pasts.append(past)
        return lengths, pasts

    @torch.inference_mode()
    def forward_batch(self, rows, caches=None):
        """Last logits [sequences, vocabulary], plus one reference-format KV cache per packed sequence."""
        if caches is None and isinstance(rows, (list, tuple)):
            caches = [None] * len(rows)
        lengths, pasts = self._batch_layout(rows, caches)
        ids = torch.cat(rows, dim=1)[0]
        if bool(((ids < 0) | (ids >= self.config.vocab_size)).any()):
            raise ReferenceArithmeticError("Packed input token outside vocabulary")
        config, kernels = self.config, self.kernels
        heads, kv_heads, dim = config.num_attention_heads, config.num_key_value_heads, self.head_dim
        spans = [(length, past + length, past) for length, past in zip(lengths, pasts)]
        layout = kernels.attention_layout(spans)
        positions = torch.tensor(
            [p + i for length, p in zip(lengths, pasts) for i in range(length)], dtype=torch.long, device=self.device
        )
        sine, cosine = self._rope_sine[positions], self._rope_cosine[positions]
        hidden = self.model.model.embed_tokens.weight[ids].float()
        flag = kernels.new_error_flag()
        new_caches = [[] for _ in rows]
        epsilon = float(config.rms_norm_eps)
        for number, layer in enumerate(self.model.model.layers):
            attention = layer.self_attn
            normalized = kernels.rms_norm(hidden, layer.input_layernorm.weight, epsilon, error_flag=flag)
            q = kernels.rope(self._project(normalized, attention.q_proj, flag), cosine, sine, heads, error_flag=flag)
            k = kernels.rope(self._project(normalized, attention.k_proj, flag), cosine, sine, kv_heads, error_flag=flag)
            v = self._project(normalized, attention.v_proj, flag).reshape(-1, kv_heads, dim).transpose(0, 1)
            key_parts, value_parts = k.split(lengths, dim=1), v.split(lengths, dim=1)
            keys, values = [], []
            for key, value, cache in zip(key_parts, value_parts, caches):
                if cache is not None:
                    old_k, old_v = cache[number]
                    keys.append(old_k[0])
                    values.append(old_v[0])
                keys.append(key)
                values.append(value)
            # Pack all prefixes and new tokens with two copies per layer, independent of the sequence count.
            # Returned cache entries are views into these bounded slabs; attention still sees per-sequence ranges.
            packed_key, packed_value = torch.cat(keys, dim=1), torch.cat(values, dim=1)
            sizes = [span[1] for span in spans]
            for index, (key, value) in enumerate(zip(packed_key.split(sizes, 1), packed_value.split(sizes, 1))):
                new_caches[index].append((key[None], value[None]))
            mixed = kernels.attention_packed(
                q,
                packed_key,
                packed_value,
                layout,
                heads // kv_heads,
                float(self._attention_scale),
                error_flag=flag,
            )
            hidden = kernels.add(hidden, self._project(mixed, attention.o_proj, flag), error_flag=flag)
            normalized = kernels.rms_norm(hidden, layer.post_attention_layernorm.weight, epsilon, error_flag=flag)
            gated = kernels.silu_mul(
                self._project(normalized, layer.mlp.gate_proj, flag),
                self._project(normalized, layer.mlp.up_proj, flag),
                error_flag=flag,
            )
            hidden = kernels.add(hidden, self._project(gated, layer.mlp.down_proj, flag), error_flag=flag)
        offset, last = 0, []
        for length in lengths:
            offset += length
            last.append(offset - 1)
        selected = hidden[torch.tensor(last, dtype=torch.long, device=self.device)]
        final = kernels.rms_norm(selected, self.model.model.norm.weight, epsilon, error_flag=flag)
        logits = self._project(final, self.model.lm_head, flag)
        kernels.raise_if_error(flag)
        return logits, tuple(tuple(cache) for cache in new_caches)

    @torch.inference_mode()
    def _prepare_generation(
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
        # Same supported greedy options as the serial oracle; validate the whole request before the first forward.
        if (
            kwargs
            or do_sample is not False
            or num_beams != 1
            or num_return_sequences != 1
            or type(use_cache) is not bool
        ):
            raise ReferenceArithmeticError("Only the declared plain greedy options are supported")
        if (
            not isinstance(input_ids, torch.Tensor)
            or input_ids.ndim != 2
            or input_ids.dtype != torch.long
            or input_ids.device != self.device
            or not input_ids.numel()
            or not 1 <= input_ids.shape[0] <= MAX_BATCH
            or bool(((input_ids < 0) | (input_ids >= self.config.vocab_size)).any())
        ):
            raise ReferenceArithmeticError("Generation needs 1..128 nonempty integer rows on the model device")
        if type(max_new_tokens) is not int or max_new_tokens < 1:
            raise ReferenceArithmeticError("max_new_tokens must be a positive integer")
        mask = torch.ones_like(input_ids, dtype=torch.bool) if attention_mask is None else attention_mask
        if mask.shape != input_ids.shape or mask.device != self.device or bool(((mask != 0) & (mask != 1)).any()):
            raise ReferenceArithmeticError("Invalid attention mask")
        mask = mask.bool()
        eos = self.generation_config.eos_token_id if eos_token_id is None else eos_token_id
        ends = [] if eos is None else [eos] if type(eos) is int else eos
        if not isinstance(ends, (list, tuple)) or any(
            type(t) is not int or not 0 <= t < self.config.vocab_size for t in ends
        ):
            raise ReferenceArithmeticError("Invalid EOS token ids")
        pad = self.generation_config.pad_token_id if pad_token_id is None else pad_token_id
        pad = ends[0] if pad is None and ends else pad
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
        histories = []
        for row, allowed in zip(input_ids, mask):
            indices = allowed.nonzero().flatten()
            if not indices.numel() or not bool(allowed[indices[0] :].all()):
                raise ReferenceArithmeticError("Packed generation accepts nonempty left-padded prompts")
            prompt = row[indices][None]
            if prompt.shape[1] + max_new_tokens > self.max_context:
                raise ReferenceArithmeticError("Requested prompt/token budget exceeds the context limit")
            histories.append(prompt)
        return histories, ends, pad, penalty

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
        histories, ends, pad, penalty = self._prepare_generation(
            input_ids,
            attention_mask,
            max_new_tokens=max_new_tokens,
            do_sample=do_sample,
            use_cache=use_cache,
            eos_token_id=eos_token_id,
            pad_token_id=pad_token_id,
            repetition_penalty=repetition_penalty,
            num_beams=num_beams,
            num_return_sequences=num_return_sequences,
            **kwargs,
        )
        active = list(range(len(histories)))
        caches = None
        outputs = [[] for _ in histories]
        for _ in range(max_new_tokens):
            current = [row[:, -1:] for row in histories] if use_cache and caches is not None else histories
            scores, new_caches = self.forward_batch(current, caches if use_cache else None)
            if penalty != 1.0:
                inverse = ops.reciprocal(torch.tensor(penalty, dtype=torch.float32, device=self.device))
                for i, history in enumerate(histories):
                    indices = history.unique()
                    selected = scores[i, indices]
                    scores[i, indices] = torch.where(
                        selected < 0, ops.mul(selected, penalty), ops.mul(selected, inverse)
                    )
            maximum = scores.max(dim=1, keepdim=True).values
            ids = torch.arange(self.config.vocab_size, device=self.device)[None]
            chosen = torch.where(scores == maximum, ids, self.config.vocab_size).amin(dim=1)
            survivors, next_histories = [], []
            for i, token in enumerate(chosen.tolist()):
                outputs[active[i]].append(token)
                if token not in ends:
                    survivors.append(i)
                    next_histories.append(torch.cat((histories[i], chosen[i].reshape(1, 1)), dim=1))
            if not survivors:
                break
            active = [active[i] for i in survivors]
            histories = next_histories
            caches = [new_caches[i] for i in survivors] if use_cache else None
        completion = torch.full((len(outputs), max(map(len, outputs))), pad, dtype=torch.long, device=self.device)
        for i, row in enumerate(outputs):
            completion[i, : len(row)] = torch.tensor(row, dtype=torch.long, device=self.device)
        return torch.cat((input_ids, completion), dim=1)
