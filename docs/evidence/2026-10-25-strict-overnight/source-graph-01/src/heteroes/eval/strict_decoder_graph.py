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
from heteroes.eval.reference_ops import ReferenceArithmeticError
from heteroes.eval.strict_decoder import describe_graph
from heteroes.eval.strict_decoder_packed import StrictDecoderPacked

GRAPH_BACKEND = "decoder_pairwise_f32_cuda_graph_v1_experimental"
DEFAULT_GRAPH_BYTES = 1024**3


def graph_memory_bound(config, capacity, context, dim):
    """Conservative tensor-payload admission budget; excludes existing weights/RoPE and CUDA driver state.

    Include both packed prefill and fixed KV, seen flags, upper-bounded non-reused decode intermediates,
    warmup snapshots and a 64 MiB allocation margin. Actual allocator peaks remain separate receipts.
    """
    h, q, kv = config.hidden_size, config.num_attention_heads * dim, config.num_key_value_heads * dim
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
    return 2 * cache + intermediates + 2 * capacity * config.vocab_size + 64 * 1024**2


class _DecodeSession:
    def __init__(self, backend, capacity, signature):
        self.backend, self.capacity, self.signature = weakref.proxy(backend), capacity, signature
        self.context, self.device = backend.max_context, backend.device
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
        self.graph = self.capture_key = None
        self.capture_count, self.closed = 0, False
        self.penalty = self.inverse = 1.0

    def buffers(self):
        return chain(
            self.caches,
            (self.seen, self.tokens, self.lengths, self.flag),
            (t for t in (self.owners, self.ranges, self.positions, self.result) if t is not None),
        )

    @torch.inference_mode()
    def clear(self):
        for tensor in chain(self.caches, (self.seen, self.tokens, self.lengths, self.flag)):
            tensor.zero_()

    def drop_capture(self):
        self.graph, self.capture_key = None, None

    def close(self):
        if not self.closed:
            self.stream.synchronize()
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

    def read(self):
        result = self.result.tolist()  # one synchronized publication includes every arithmetic error bit
        status = result[-1]
        if status & 1:
            raise ReferenceArithmeticError("Nonfinite reference arithmetic")
        if status:
            raise ReferenceArithmeticError("Reference decode layout/domain failure")
        return result[:-1]

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
            self.backend._decode_core(self)
        self.graph, self.capture_key = graph, key
        self.capture_count += 1


class StrictDecoderGraph(StrictDecoderPacked):
    def __init__(self, model, *, max_context=256, allow_fixture=False, max_graph_bytes=DEFAULT_GRAPH_BYTES):
        if type(max_graph_bytes) is not int or max_graph_bytes < 1:
            raise ReferenceArithmeticError("Captured decode needs a positive integer memory budget")
        super().__init__(model, max_context=max_context, allow_fixture=allow_fixture)
        self.max_graph_bytes = max_graph_bytes
        self._session, self._call_lock = None, threading.Lock()
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

    def _session_for(self, capacity):
        if next(self.model.parameters()).device != self.device:
            raise ReferenceArithmeticError("Captured decoder model moved away from its CUDA device")
        graph = describe_graph(self.model, self.max_context)
        if graph != self.identity["graph"]:
            raise ReferenceArithmeticError("Captured decoder graph configuration changed")
        signature = tuple(
            (name, p.data_ptr(), tuple(p.shape), tuple(p.stride()), p.dtype, p.device)
            for name, p in self.model.named_parameters(remove_duplicate=False)
        )
        stream = torch.cuda.current_stream(self.device)
        if self._session is not None and (
            self._session.capacity != capacity or self._session.signature != signature or self._session.stream != stream
        ):
            self._release_graph()
        if self._session is None:
            self._session = _DecodeSession(self, capacity, signature)
        return self._session

    def _decode_core(self, state):
        config, kernels, flag = self.config, self.kernels, state.flag
        state.flag.zero_()
        active = state.owners.numel()
        heads, kv_heads, dim = config.num_attention_heads, config.num_key_value_heads, self.head_dim
        state.decode.layout(
            state.owners, state.lengths, state.ranges, state.positions, flag, state.capacity, self.max_context
        )
        ids = state.tokens[state.owners]
        hidden = self.model.model.embed_tokens.weight[ids].float()
        cosine, sine = self._rope_cosine[state.positions], self._rope_sine[state.positions]
        layout = sc._PackedAttentionLayout(state.ranges, active, state.capacity * self.max_context, self.max_context)
        epsilon = float(config.rms_norm_eps)
        for number, layer in enumerate(self.model.model.layers):
            attention = layer.self_attn
            normalized = kernels.rms_norm(hidden, layer.input_layernorm.weight, epsilon, error_flag=flag)
            q = kernels.rope(self._project(normalized, attention.q_proj, flag), cosine, sine, heads, error_flag=flag)
            k = kernels.rope(self._project(normalized, attention.k_proj, flag), cosine, sine, kv_heads, error_flag=flag)
            v = self._project(normalized, attention.v_proj, flag)
            keys, values = state.caches[2 * number : 2 * number + 2]
            state.decode.store(k, v, state.ranges, keys, values)
            mixed = kernels.attention_packed(
                q, keys, values, layout, heads // kv_heads, float(self._attention_scale), error_flag=flag
            )
            hidden = kernels.add(hidden, self._project(mixed, attention.o_proj, flag), error_flag=flag)
            normalized = kernels.rms_norm(hidden, layer.post_attention_layernorm.weight, epsilon, error_flag=flag)
            gated = kernels.silu_mul(
                self._project(normalized, layer.mlp.gate_proj, flag),
                self._project(normalized, layer.mlp.up_proj, flag),
                error_flag=flag,
            )
            hidden = kernels.add(hidden, self._project(gated, layer.mlp.down_proj, flag), error_flag=flag)
        normalized = kernels.rms_norm(hidden, self.model.model.norm.weight, epsilon, error_flag=flag)
        logits = self._project(normalized, self.model.lm_head, flag)
        state.decode.greedy(
            logits, state.seen, state.owners, state.tokens, state.result, flag, state.penalty, state.inverse
        )
        state.decode.publish(state.owners, state.lengths, flag, state.result, advance=True)

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
                return super().generate(input_ids, attention_mask, **options)
            capacity = len(histories)
            if graph_memory_bound(self.config, capacity, self.max_context, self.head_dim) > self.max_graph_bytes:
                raise ReferenceArithmeticError("Captured decode exceeds its explicit memory budget")
            state = self._session_for(capacity)
            state.clear()
            lengths = [row.shape[1] for row in histories]
            state.lengths.copy_(torch.tensor(lengths, dtype=torch.int32, device=self.device))
            for owner, row in enumerate(histories):
                state.seen[owner, row[0]] = 1
            inverse = float(ops.reciprocal(torch.tensor(penalty, dtype=torch.float32, device=self.device)).item())
            active = list(range(capacity))
            state.select(active, penalty, inverse)
            logits, caches = self.forward_batch(histories)
            state.prefix(caches, lengths)
            del caches
            state.flag.zero_()
            state.decode.greedy(
                logits, state.seen, state.owners, state.tokens, state.result, state.flag, penalty, inverse
            )
            state.decode.publish(state.owners, state.lengths, state.flag, state.result, advance=False)
            chosen = state.read()
            del logits
            outputs = [[] for _ in histories]
            for step in range(max_new_tokens):
                survivors = []
                for owner, token in zip(active, chosen):
                    outputs[owner].append(token)
                    if token not in ends:
                        survivors.append(owner)
                if not survivors or step + 1 == max_new_tokens:
                    break
                active = survivors
                key = state.select(active, penalty, inverse)
                if state.graph is None:
                    state.capture(key)
                state.graph.replay()
                chosen = state.read()
            completion = torch.full((capacity, max(map(len, outputs))), pad, dtype=torch.long, device=self.device)
            for i, row in enumerate(outputs):
                completion[i, : len(row)] = torch.tensor(row, dtype=torch.long, device=self.device)
            return torch.cat((input_ids, completion), dim=1)
        except BaseException:
            self._release_graph()
            raise
        finally:
            if self._session is not None:
                self._session.clear()
                self._session.stream.synchronize()
            self._call_lock.release()
