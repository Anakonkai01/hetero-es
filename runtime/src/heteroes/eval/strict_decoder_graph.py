"""Experimental bounded captured decode over the shared strict decoder graph.

Prefill uses the packed oracle-compatible path. Decode keeps fixed KV slots for original sequence owners;
EOS removes owners from the captured query batch without moving another sequence's cache. A single capture
is retained, weights are read through their live pointers, and request boundaries clear all KV/seen state.
"""

import hashlib
from itertools import chain
from pathlib import Path
import struct
import threading
import weakref

import torch

from heteroes.canonical import canonical_json_hash
from heteroes.eval import reference_ops as ops
from heteroes.eval import strict_cuda as sc
from heteroes.eval import strict_decode_cuda
from heteroes.eval.reference_ops import ReferenceArithmeticError, StrictMemoryBudget, StrictTransportError
from heteroes.eval.strict_decoder import describe_graph
from heteroes.eval.strict_decoder_packed import StrictDecoderPacked

GRAPH_BACKEND = "decoder_pairwise_f32_cuda_graph_v1_experimental"
DEFAULT_GRAPH_BYTES = 1024**3


def graph_memory_bound(config, capacity, context, dim, *, prompt_tokens=None):
    """Conservative tensor-payload admission budget; excludes existing weights/RoPE and CUDA driver state.

    Include both packed prefill and fixed KV, seen flags, upper-bounded non-reused decode intermediates,
    warmup snapshots and a 64 MiB allocation margin. Actual allocator peaks remain separate receipts.
    """
    h, q, kv = config.hidden_size, config.num_attention_heads * dim, config.num_key_value_heads * dim
    prompt_tokens = capacity * context if prompt_tokens is None else prompt_tokens
    cache = 2 * config.num_hidden_layers * capacity * context * kv * 4
    intermediates = (
        4
        * capacity
        * (
            config.num_hidden_layers * (16 * h + 8 * q + 8 * kv + 4 * config.intermediate_size)
            + 2 * config.vocab_size
            + 8 * dim
        )
    )
    seen = capacity * config.vocab_size
    prefix_cache = 2 * config.num_hidden_layers * prompt_tokens * kv * 4
    # Prefill intermediates cover all packed prompt tokens, rather than only the decode batch. Layers
    # retain their published KV, but their hidden/projection temporaries are released as the loop advances.
    prefill_workspace = 4 * prompt_tokens * (16 * h + 8 * q + 8 * kv + 4 * config.intermediate_size)
    return max(2 * cache + intermediates + 2 * seen, cache + prefix_cache + prefill_workspace + seen) + 64 * 1024**2


def request_context(max_context, lengths, max_new_tokens):
    """Physical KV slots per owner: the request's longest prompt plus its token budget, rounded up to 16 and never above
    the configured context. Admission and the memory bound still use the configured context (conservative)."""
    return min(max_context, -(-(max(lengths) + max_new_tokens) // 16) * 16)


class _DecodeSession:
    def __init__(self, backend, capacity, signature, context=None):
        self.backend, self.capacity, self.signature = weakref.proxy(backend), capacity, signature
        self.context, self.device = backend.max_context if context is None else context, backend.device
        self.stream = torch.cuda.current_stream(self.device)
        self.decode = strict_decode_cuda.DecodeKernels(backend.kernels)
        c, dim = backend.config, backend.head_dim
        shape = (c.num_key_value_heads, capacity * self.context, dim)
        self.caches = tuple(
            torch.zeros(shape, dtype=torch.float32, device=self.device) for _ in range(2 * c.num_hidden_layers)
        )
        self.seen = torch.zeros((capacity, c.vocab_size), dtype=torch.uint8, device=self.device)
        self.tokens = torch.zeros(capacity, dtype=torch.long, device=self.device)
        self.lengths = torch.zeros(capacity, dtype=torch.int32, device=self.device)
        self.flag = backend.kernels.new_error_flag()
        self.owners = self.ranges = self.positions = self.result = None
        self.graph = self.capture_key = self.last_logits = None
        self.capture_count, self.closed = 0, False
        self.penalty = self.inverse = 1.0
        # Two pinned result slots let the host read step t while the GPU already runs step t+1.
        self.staged = tuple(torch.empty(capacity + 1, dtype=torch.long, pin_memory=True) for _ in range(2))
        self.events = tuple(torch.cuda.Event() for _ in range(2))
        self.slot = 0

    def buffers(self):
        return chain(
            self.caches,
            (self.seen, self.tokens, self.lengths, self.flag),
            (t for t in (self.owners, self.ranges, self.positions, self.result, self.last_logits) if t is not None),
        )

    @torch.inference_mode()
    def clear(self):
        if self.caches:
            torch._foreach_zero_(list(self.caches))
        for tensor in (self.seen, self.tokens, self.lengths, self.flag):
            tensor.zero_()

    def drop_capture(self):
        self.graph, self.capture_key, self.last_logits = None, None, None

    def close(self):
        if not self.closed:
            self.stream.synchronize()
            with torch.cuda.stream(self.stream):
                self.clear()
            self.stream.synchronize()
            self.drop_capture()
            self.closed = True

    def select(self, active, penalty, inverse):
        key = (len(active), struct.pack("<ff", penalty, inverse), penalty != 1.0)
        if self.owners is None or self.owners.numel() != len(active):
            self.drop_capture()
            self.owners = torch.empty(len(active), dtype=torch.long, device=self.device)
            self.ranges = torch.empty((len(active), 3), dtype=torch.int32, device=self.device)
            self.positions = torch.empty(len(active), dtype=torch.long, device=self.device)
            self.result = torch.empty(len(active) + 1, dtype=torch.long, device=self.device)
        elif self.capture_key is not None and self.capture_key != key:
            self.drop_capture()
        self.owners.copy_(torch.tensor(active, dtype=torch.long, device=self.device))
        self.penalty, self.inverse = penalty, inverse
        return key

    def prefix(self, caches, lengths):
        """Packed prefill returns disjoint views of one contiguous slab per layer and kind."""
        total, offset, spans = sum(lengths), 0, []
        for owner, length in enumerate(lengths):
            spans.append((offset, length, owner * self.context))
            offset += length
        spans = torch.tensor(spans, dtype=torch.int32, device=self.device)
        heads, dim = self.backend.config.num_key_value_heads, self.backend.head_dim
        slabs = getattr(caches, "slabs", None)
        if slabs is not None and len(slabs) == self.backend.config.num_hidden_layers:
            # The packed prefill's own slabs: one shape check per slab instead of one per sequence view.
            for layer, pair in enumerate(slabs):
                if any(s.shape != (heads, total, dim) or not s.is_contiguous() for s in pair):
                    raise ReferenceArithmeticError("Captured decode needs the verified packed prefill slabs")
                self.decode.prefix(*pair, spans, *self.caches[2 * layer : 2 * layer + 2])
            return
        for layer in range(self.backend.config.num_hidden_layers):
            source = []
            for kind in (0, 1):
                first = caches[0][layer][kind][0]
                storage = first.untyped_storage().data_ptr()
                offset = 0
                for cache, length in zip(caches, lengths):
                    item = cache[layer][kind][0]
                    if (
                        item.shape != (heads, length, dim)
                        or item.stride() != (total * dim, dim, 1)
                        or item.storage_offset() != offset * dim
                        or item.untyped_storage().data_ptr() != storage
                    ):
                        raise ReferenceArithmeticError("Captured decode needs the verified packed prefill slabs")
                    offset += length
                source.append(first.as_strided((heads, total, dim), (total * dim, dim, 1)))
            self.decode.prefix(*source, spans, *self.caches[2 * layer : 2 * layer + 2])

    @staticmethod
    def check(status):
        if status & 8:
            raise StrictTransportError("Strict kernel data transport timed out")
        if status & 1:
            raise ReferenceArithmeticError("Nonfinite reference arithmetic")
        if status:
            raise ReferenceArithmeticError("Reference decode layout/domain failure")

    def read(self):
        result = self.result.tolist()  # one synchronized publication includes every arithmetic error bit
        self.check(result[-1])
        return result[:-1]

    def launch(self):
        """Replay one decode step and stage its published result (tokens + status) without waiting for it."""
        self.graph.replay()
        self.slot ^= 1
        count = self.owners.numel() + 1
        self.staged[self.slot][:count].copy_(self.result, non_blocking=True)
        self.events[self.slot].record(self.stream)
        return self.slot, count

    def wait(self, handle):
        """Return (tokens, status) of a launched step; the status is the step's complete error publication."""
        slot, count = handle
        self.events[slot].synchronize()
        result = self.staged[slot][:count].tolist()
        return result[:-1], result[-1]

    @torch.inference_mode()
    def undo(self, owners, previous, speculative, histories, outputs):
        """Remove one speculative step's effects: its length advance, token and newly set seen flags.

        Its KV writes sit at each owner's next position, which the replacement step overwrites before reading.
        """
        index = torch.tensor(owners, dtype=torch.long, device=self.device)
        self.lengths[index] -= 1
        self.tokens[index] = torch.tensor(previous, dtype=torch.long, device=self.device)
        for owner, token in zip(owners, speculative):
            if token not in outputs[owner] and token not in histories[owner][0].tolist():
                self.seen[owner, token] = 0

    def capture(self, key):
        # Warmup compiles every specialization outside capture. Restore mutable selector state afterwards;
        # the next replay overwrites the single KV position touched by warmup before reading that position.
        saved = tuple(t.clone() for t in (self.tokens, self.lengths, self.seen))
        self.backend._decode_core(self)
        self.backend.kernels.raise_if_error(self.flag)
        for tensor, previous in zip((self.tokens, self.lengths, self.seen), saved):
            tensor.copy_(previous)
        del saved
        graph = torch.cuda.CUDAGraph()
        with torch.cuda.graph(graph):
            self.last_logits = self.backend._decode_core(self)
        self.graph, self.capture_key = graph, key
        self.capture_count += 1


class StrictDecoderGraph(StrictDecoderPacked):
    def __init__(
        self, model, *, max_context=256, allow_fixture=False, max_graph_bytes=DEFAULT_GRAPH_BYTES, frozen_int8=False
    ):
        if type(max_graph_bytes) is not int or max_graph_bytes < 1:
            raise ReferenceArithmeticError("Captured decode needs a positive integer memory budget")
        super().__init__(model, max_context=max_context, allow_fixture=allow_fixture, frozen_int8=frozen_int8)
        self.max_graph_bytes = max_graph_bytes
        self._session, self._call_lock = None, threading.Lock()
        self._inverse_cache = None
        self.identity = {
            **self.identity,
            "backend": GRAPH_BACKEND,
            "decodeGraphSourceSha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "decodeKernelsSourceSha256": hashlib.sha256(Path(strict_decode_cuda.__file__).read_bytes()).hexdigest(),
            "maxGraphBytes": max_graph_bytes,
            "cachePolicy": "clear_on_request_boundary",
            "maxRetainedCaptures": 1,
        }
        self.fingerprint = canonical_json_hash(self.identity)

    def buffers(self, *args, **kwargs):
        return chain(super().buffers(*args, **kwargs), () if self._session is None else self._session.buffers())

    def _release_graph(self):
        if self._session is not None:
            self._session.close()
            self._session = None

    def release_graph(self):
        if not self._call_lock.acquire(blocking=False):
            raise ReferenceArithmeticError("Captured decode refuses concurrent use")
        try:
            self._release_graph()
        finally:
            self._call_lock.release()

    def _session_for(self, capacity, context=None):
        if next(self.model.parameters()).device != self.device:
            raise ReferenceArithmeticError("Captured decoder model moved away from its CUDA device")
        graph = describe_graph(self.model, self.max_context, frozen_int8=self.frozen_int8)
        if graph != self.identity["graph"]:
            raise ReferenceArithmeticError("Captured decoder graph configuration changed")
        signature = tuple(
            (name, p.data_ptr(), tuple(p.shape), tuple(p.stride()), p.dtype, p.device)
            for name, p in self.model.named_parameters(remove_duplicate=False)
        )
        if self.frozen_int8:
            signature += tuple(
                ("buffer:" + name, b.data_ptr(), tuple(b.shape), tuple(b.stride()), b.dtype, b.device)
                for name, b in self.model.named_buffers(remove_duplicate=False)
            )
        stream = torch.cuda.current_stream(self.device)
        context = self.max_context if context is None else context
        if self._session is not None and (
            self._session.capacity != capacity
            or self._session.context != context
            or self._session.signature != signature
            or self._session.stream != stream
        ):
            self._release_graph()
        if self._session is None:
            self._session = _DecodeSession(self, capacity, signature, context)
        return self._session

    def _request_workspace_bytes(self, capacity=1):
        return 0

    def _decode_project(self, value, module, flag):
        return self._project(value, module, flag)

    def _decode_project_many(self, value, modules, flag):
        return self._project_many(value, modules, flag)

    def _decode_norm_project_many(self, hidden, norm, epsilon, modules, flag):
        """RMSNorm whose output feeds only these projections (an adapter may fuse the two)."""
        return self._decode_project_many(self.kernels.rms_norm(hidden, norm, epsilon, error_flag=flag), modules, flag)

    def _decode_norm_project(self, hidden, norm, epsilon, module, flag):
        return self._decode_project(self.kernels.rms_norm(hidden, norm, epsilon, error_flag=flag), module, flag)

    def _decode_gated_project(self, gate, up, module, flag):
        """SiLU gate whose output feeds only this projection (an adapter may fuse the two)."""
        return self._decode_project(self.kernels.silu_mul(gate, up, error_flag=flag), module, flag)

    def _decode_attention_input(self, hidden, layer, epsilon, cosine, sine, state, keys, values, flag):
        """Rotated decode queries [heads, rows, dim]; rotated keys and values are stored in this layer's cache."""
        attention, kernels = layer.self_attn, self.kernels
        q, k, v = self._decode_norm_project_many(
            hidden,
            layer.input_layernorm.weight,
            epsilon,
            (attention.q_proj, attention.k_proj, attention.v_proj),
            flag,
        )
        q = kernels.rope(q, cosine, sine, self.config.num_attention_heads, error_flag=flag)
        k = kernels.rope(k, cosine, sine, self.config.num_key_value_heads, error_flag=flag)
        state.decode.store(k, v, state.ranges, keys, values)
        return q

    def _decode_residual_project(self, hidden, value, module, flag):
        """strict_add(hidden, projection of value): the residual update (an adapter may fuse the add)."""
        return self.kernels.add(hidden, self._decode_project(value, module, flag), error_flag=flag)

    def _decode_mlp(self, hidden, layer, epsilon, flag):
        """hidden + down(silu(gate(norm(hidden))) * up(norm(hidden)))."""
        gate, up = self._decode_norm_project_many(
            hidden, layer.post_attention_layernorm.weight, epsilon, (layer.mlp.gate_proj, layer.mlp.up_proj), flag
        )
        return self.kernels.add(
            hidden, self._decode_gated_project(gate, up, layer.mlp.down_proj, flag), error_flag=flag
        )

    def _generation_begin(self):
        """Optional operator request state, always prepared while the generation lock is held."""

    def _generation_end(self):
        """Release request state before allowing another caller to enter."""

    def _generation_decode_ready(self, capacity, penalty):
        """Optional decode-only request preparation after admission and before prefill/capture."""

    def _inverse_for(self, penalty):
        key = struct.pack("<f", penalty)
        if self._inverse_cache is None or self._inverse_cache[0] != key:
            inverse = float(ops.reciprocal(torch.tensor(penalty, dtype=torch.float32, device=self.device)).item())
            self._inverse_cache = (key, inverse)
        return self._inverse_cache[1]

    def _decode_output(self, hidden, epsilon, state):
        logits = self._decode_norm_project(
            hidden, self.model.model.norm.weight, epsilon, self.model.lm_head, state.flag
        )
        state.decode.greedy(
            logits, state.seen, state.owners, state.tokens, state.result, state.flag, state.penalty, state.inverse
        )
        return logits

    def _decode_core(self, state):
        config, kernels, flag = self.config, self.kernels, state.flag
        state.flag.zero_()
        active = state.owners.numel()
        heads, kv_heads, dim = config.num_attention_heads, config.num_key_value_heads, self.head_dim
        state.decode.layout(
            state.owners, state.lengths, state.ranges, state.positions, flag, state.capacity, state.context
        )
        ids = state.tokens[state.owners]
        hidden = self.model.model.embed_tokens.weight[ids].float()
        cosine, sine = self._rope_cosine[state.positions], self._rope_sine[state.positions]
        layout = sc._PackedAttentionLayout(state.ranges, active, state.capacity * state.context, state.context)
        epsilon = float(config.rms_norm_eps)
        for number, layer in enumerate(self.model.model.layers):
            keys, values = state.caches[2 * number : 2 * number + 2]
            q = self._decode_attention_input(hidden, layer, epsilon, cosine, sine, state, keys, values, flag)
            mixed = kernels.attention_packed(
                q, keys, values, layout, heads // kv_heads, float(self._attention_scale), error_flag=flag
            )
            hidden = self._decode_residual_project(hidden, mixed, layer.self_attn.o_proj, flag)
            hidden = self._decode_mlp(hidden, layer, epsilon, flag)
        logits = self._decode_output(hidden, epsilon, state)
        state.decode.publish(state.owners, state.lengths, flag, state.result, advance=True)
        return logits

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
        options = dict(
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
        histories, ends, pad, penalty = self._prepare_generation(input_ids, attention_mask, **options)
        if not self._call_lock.acquire(blocking=False):
            raise ReferenceArithmeticError("Captured decode refuses concurrent use")
        try:
            if not use_cache:
                self._release_graph()
                self._generation_begin()
                return super().generate(input_ids, attention_mask, **options)
            capacity = len(histories)
            lengths = [row.shape[1] for row in histories]
            if (
                graph_memory_bound(self.config, capacity, self.max_context, self.head_dim, prompt_tokens=sum(lengths))
                + self._request_workspace_bytes(capacity)
                > self.max_graph_bytes
            ):
                raise StrictMemoryBudget("Captured decode exceeds its explicit memory budget")
            state = self._session_for(capacity, request_context(self.max_context, lengths, max_new_tokens))
            self._generation_begin()
            self._generation_decode_ready(capacity, penalty)
            state.clear()
            state.lengths.copy_(torch.tensor(lengths, dtype=torch.int32, device=self.device))
            for owner, row in enumerate(histories):
                state.seen[owner, row[0]] = 1
            inverse = self._inverse_for(penalty)
            active = list(range(capacity))
            state.select(active, penalty, inverse)
            # The prefill status is checked once the cache copy and first selection are queued behind it.
            prefill_flag = self.kernels.new_error_flag()
            logits, caches = self.forward_batch(histories, error_flag=prefill_flag, _validated=True)
            state.prefix(caches, lengths)
            del caches
            state.flag.zero_()
            state.decode.greedy(
                logits, state.seen, state.owners, state.tokens, state.result, state.flag, penalty, inverse
            )
            state.decode.publish(state.owners, state.lengths, state.flag, state.result, advance=False)
            self.kernels.raise_if_error(prefill_flag)
            chosen = state.read()
            del logits
            outputs = [[] for _ in histories]
            # One step stays queued ahead of the host. Rows are computed independently, so a step queued
            # before some owners emitted EOS is still exact for the survivors; the extra rows are dropped. If
            # that step reports a failure, which could come from a dropped row, it is undone and recomputed
            # with only the survivors, exactly as the unpipelined loop would have run it.
            pending = None
            for step in range(max_new_tokens):
                survivors = []
                for owner, token in zip(active, chosen):
                    outputs[owner].append(token)
                    if token not in ends:
                        survivors.append(owner)
                if not survivors or step + 1 == max_new_tokens:
                    break
                if pending is not None and survivors == active:
                    queued = state.launch() if step + 2 < max_new_tokens else None
                    chosen, status = state.wait(pending)
                    state.check(status)
                    pending = queued
                    continue
                if pending is not None:
                    speculative, status = state.wait(pending)
                    pending = None
                    if not status:
                        keep = set(survivors)
                        chosen = [token for owner, token in zip(active, speculative) if owner in keep]
                        active = survivors
                        continue
                    state.undo(active, chosen, speculative, histories, outputs)
                    active = survivors
                    key = state.select(active, penalty, inverse)
                    if state.graph is None:
                        state.capture(key)
                    state.graph.replay()
                    chosen = state.read()
                    continue
                active = survivors
                key = state.select(active, penalty, inverse)
                if state.graph is None:
                    state.capture(key)
                current = state.launch()
                pending = state.launch() if step + 2 < max_new_tokens else None
                chosen, status = state.wait(current)
                state.check(status)
            width = max(map(len, outputs))
            completion = torch.tensor(
                [row + [pad] * (width - len(row)) for row in outputs], dtype=torch.long, device=self.device
            )
            return torch.cat((input_ids, completion), dim=1)
        except BaseException:
            self._release_graph()
            raise
        finally:
            try:
                self._generation_end()
                if self._session is not None:
                    self._session.clear()
                    self._session.stream.synchronize()
            finally:
                self._call_lock.release()
