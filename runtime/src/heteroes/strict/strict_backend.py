"""
The strict B22 decoder as a Recipe v3 decoder (`strict_b22_v1`, ADR-013): greedy generation for `study.evaluation`.

One `IntegerDecoderGraph` per live model reads the live FP16 weights in place, so the executor's in-place perturb and
exact restore are seen by the next generation and no second weight set exists. The engine is kept for the model's
lifetime and replaced only when a longer context is needed. Generation settings come from the pinned generation config,
as the library would build them for greedy decoding: its EOS ids and repetition penalty; any other active processor is
refused before decoding (`compact_decode.decode_settings`).

Failures keep their meaning (executor.py maps them): over the explicit memory budget -> `StrictMemoryBudget`
(OUT_OF_MEMORY), transport timeout -> `StrictTransportError` (infrastructure), nonfinite or out-of-domain strict
arithmetic -> `ReferenceArithmeticError` (a candidate failure, never a reward).
"""

import os
import threading
import weakref

import torch

from heteroes.strict.reference_ops import ReferenceArithmeticError

STRICT_CONTEXTS = (512, 1024, 2048, 4096)  # engine context buckets; the physical KV is sized per request anyway
GRAPH_BUDGET_FRACTION = 0.4  # default decoder memory budget: this share of the device's total memory
_engines = weakref.WeakKeyDictionary()
_lock = threading.Lock()


def context_for(tokens, limit=STRICT_CONTEXTS[-1]):
    """The engine context for `tokens` per row: the smallest bucket that holds them, never above the model's limit."""
    limit = min(limit, STRICT_CONTEXTS[-1])
    if tokens > limit:
        raise ReferenceArithmeticError(f"strict_b22_v1 supports prompt + new tokens up to {limit} for this model")
    return min(limit, next(context for context in STRICT_CONTEXTS if tokens <= context))


def graph_budget(device):
    configured = os.environ.get("HETEROES_STRICT_GRAPH_BYTES")
    if configured is not None:
        if not configured.isdigit() or int(configured) < 1:
            raise ValueError("HETEROES_STRICT_GRAPH_BYTES is a positive number of bytes")
        return int(configured)
    return int(GRAPH_BUDGET_FRACTION * torch.cuda.get_device_properties(device).total_memory)


def engine_for(model, tokens=1, decoder=None):
    """
    The strict engine of this live model with room for `tokens` (prompt + new tokens) per row: B22 over the live FP16
    weights, or (M6, `strict_int8_lora_v1`) the frozen int8 base with its FP16 adapters. `decoder`, when given, must
    match the model: a frozen base is never decoded as B22 or the other way round.
    """
    from heteroes.catalog import STRICT_INT8_LORA_DECODER
    from heteroes.strict.frozen_int8_decoder import FrozenInt8DecoderGraph
    from heteroes.strict.integer_decoder import IntegerDecoderGraph
    from heteroes.strict.reference_ops import managed_opt_in
    from heteroes.model.frozen_int8 import frozen_modules

    device = next(model.parameters()).device
    if device.type != "cuda":
        raise ReferenceArithmeticError("strict_b22_v1 runs on an NVIDIA GPU")
    frozen = next(frozen_modules(model), None) is not None
    if decoder is not None and frozen != (decoder == STRICT_INT8_LORA_DECODER):
        raise ReferenceArithmeticError(f"The model's base does not match the {decoder} decoder")
    context = context_for(tokens, model.config.max_position_embeddings)
    with _lock:
        engine = _engines.get(model)
        if engine is not None and engine.max_context >= context:
            return engine
        if engine is not None:
            engine.release_graph()  # one engine per model: free the old capture before the larger one exists
        with managed_opt_in():
            if frozen:
                engine = FrozenInt8DecoderGraph(model, max_context=context, max_graph_bytes=graph_budget(device))
            else:
                engine = IntegerDecoderGraph(
                    model, magnitude_bits=22, max_context=context, max_graph_bytes=graph_budget(device)
                )
        _engines[model] = engine
        return engine


def release(model):
    """Drop the strict engine of `model` (graph, buffers, KV), so its device memory can be freed; a no-op without one."""
    with _lock:
        engine = _engines.pop(model, None)
    if engine is not None:
        engine.release_graph()


def generate_ids(model, input_ids, attention_mask, max_new_tokens, eos_ids, pad_id, processors, decoder=None):
    """New token ids of greedy decoding (left-padded batch), with `pad_id` after EOS, as `model.generate` returns them."""
    penalties = [p.penalty for p in processors if type(p).__name__ == "RepetitionPenaltyLogitsProcessor"]
    if len(penalties) != len(processors) or len(penalties) > 1:
        raise ReferenceArithmeticError("strict_b22_v1 reproduces only the repetition penalty")
    engine = engine_for(model, input_ids.shape[1] + max_new_tokens, decoder)
    output = engine.generate(
        input_ids,
        attention_mask=attention_mask,
        do_sample=False,
        max_new_tokens=max_new_tokens,
        eos_token_id=list(eos_ids),
        pad_token_id=pad_id,
        repetition_penalty=float(penalties[0]) if penalties else 1.0,
        use_cache=True,
    )
    return output[:, input_ids.shape[1] :]
