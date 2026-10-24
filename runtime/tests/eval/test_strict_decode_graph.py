"""Captured decode must preserve tokens, candidate isolation, live weights and bounded ownership."""

import copy
import os

import pytest
import torch

from heteroes.eval.reference_ops import ReferenceArithmeticError
from test_strict_decoder import bits, model_for


def graph_class():
    from heteroes.eval.strict_decoder_graph import StrictDecoderGraph

    return StrictDecoderGraph


def test_graph_backend_still_requires_explicit_gpu_and_positive_memory_budget(monkeypatch):
    model = model_for("llama")
    monkeypatch.delenv("HETEROES_GPU_ACCEPTANCE", raising=False)
    with pytest.raises(ReferenceArithmeticError, match="HETEROES_GPU_ACCEPTANCE"):
        graph_class()(model)
    monkeypatch.setenv("HETEROES_GPU_ACCEPTANCE", "1")
    with pytest.raises(ReferenceArithmeticError, match="CUDA"):
        graph_class()(model)
    for limit in (0, -1, True, 1.5):
        with pytest.raises(ReferenceArithmeticError, match="budget"):
            graph_class()(model, max_graph_bytes=limit)


gpu = pytest.mark.skipif(
    os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or not torch.cuda.is_available(), reason="GPU opt-in"
)


@gpu
@pytest.mark.parametrize("family", ["qwen2", "llama", "llama-wide", "mistral"])
def test_captured_generation_matches_cpu_and_reuses_live_weights_without_candidate_kv(family):
    from heteroes.eval.strict_decoder import StrictDecoderReference

    model = model_for(family).cuda()
    backend = graph_class()(model, max_context=32, allow_fixture=True)
    ids = torch.tensor([[0, 0, 3, 5], [7, 11, 13, 17], [0, 19, 23, 29]], device="cuda")
    mask = ids != 0
    weight = model.model.layers[0].mlp.down_proj.weight
    snapshot = weight.detach().clone()
    parents = []
    session = None
    for factor in (1.0, -1.0, 1.0):
        with torch.no_grad():
            weight.copy_(snapshot * factor)
        oracle = StrictDecoderReference(copy.deepcopy(model).cpu(), max_context=32, allow_fixture=True)
        expected = oracle.generate(ids.cpu(), attention_mask=mask.cpu(), max_new_tokens=5, eos_token_id=[])
        actual = backend.generate(ids, attention_mask=mask, max_new_tokens=5, eos_token_id=[])
        assert torch.equal(actual.cpu(), expected)
        fed = [
            torch.cat((row[allowed], result[ids.shape[1] : -1]))[None]
            for row, allowed, result in zip(ids, mask, actual)
        ]
        logits = torch.cat([oracle.forward_tokens(row.cpu())[0] for row in fed])
        assert torch.equal(bits(backend._session.last_logits.cpu()), bits(logits))
        parents.append(actual.clone())
        assert backend._session is not None
        if session is None:
            session = backend._session
        assert backend._session is session and session.capture_count == 1
        assert all(not bool(t.any()) for t in session.caches)
        assert not bool(session.seen.any())
    assert torch.equal(parents[0], parents[2])
    assert torch.equal(weight.view(torch.int16), snapshot.view(torch.int16))
    assert backend.identity["hardwareQualified"] is False
    backend.release_graph()
    assert backend._session is None


@gpu
@pytest.mark.parametrize(
    "options", [{"repetition_penalty": 1.3}, {"use_cache": False}, {"eos_token_id": list(range(20))}]
)
def test_graph_generation_keeps_penalty_no_cache_and_eos_ownership(options):
    from heteroes.eval.strict_decoder_packed import StrictDecoderPacked

    model = model_for("llama-wide").cuda()
    backend = graph_class()(model, max_context=32, allow_fixture=True)
    eager = StrictDecoderPacked(model, max_context=32, allow_fixture=True)
    ids = torch.tensor([[0, 3, 5], [7, 11, 13], [0, 17, 19], [23, 29, 31]], device="cuda")
    mask = ids != 0
    actual = backend.generate(ids, attention_mask=mask, max_new_tokens=7, **options)
    expected = eager.generate(ids, attention_mask=mask, max_new_tokens=7, **options)
    assert torch.equal(actual, expected)


@gpu
def test_graph_budget_refuses_before_prefill_and_second_live_weight_binding(monkeypatch):
    model = model_for("mistral").cuda()
    backend = graph_class()(model, max_context=32, allow_fixture=True, max_graph_bytes=1)
    monkeypatch.setattr(backend, "forward_batch", lambda *a, **kw: pytest.fail("budget must be checked first"))
    with pytest.raises(ReferenceArithmeticError, match="budget"):
        backend.generate(torch.tensor([[3, 5]], device="cuda"), max_new_tokens=3, eos_token_id=[])
    assert backend._session is None


@gpu
def test_budget_accounts_for_actual_prefill_workspace_before_computation(monkeypatch):
    from heteroes.eval.strict_decoder_graph import graph_memory_bound

    model = model_for("llama-wide").cuda()
    limit = graph_memory_bound(model.config, 2, 32, 12, prompt_tokens=4)
    assert graph_memory_bound(model.config, 2, 32, 12, prompt_tokens=52) > limit
    backend = graph_class()(model, max_context=32, allow_fixture=True, max_graph_bytes=limit)
    backend.generate(torch.tensor([[3, 5], [7, 11]], device="cuda"), max_new_tokens=3, eos_token_id=[])
    monkeypatch.setattr(backend, "forward_batch", lambda *a, **kw: pytest.fail("prefill budget must be checked first"))
    with pytest.raises(ReferenceArithmeticError, match="budget"):
        backend.generate(torch.ones((2, 26), dtype=torch.long, device="cuda"), max_new_tokens=3, eos_token_id=[])
    assert backend._session is None


@gpu
def test_parameter_rebinding_invalidates_capture_but_inplace_updates_do_not():
    from heteroes.eval.strict_decoder_packed import StrictDecoderPacked

    model = model_for("mistral").cuda()
    backend = graph_class()(model, max_context=32, allow_fixture=True)
    ids = torch.tensor([[3, 5], [7, 11]], device="cuda")
    backend.generate(ids, max_new_tokens=3, eos_token_id=[])
    previous = backend._session
    module = model.model.layers[0].mlp.down_proj
    module.weight = torch.nn.Parameter(-module.weight.detach().clone())
    actual = backend.generate(ids, max_new_tokens=3, eos_token_id=[])
    expected = StrictDecoderPacked(model, max_context=32, allow_fixture=True).generate(
        ids, max_new_tokens=3, eos_token_id=[]
    )
    assert torch.equal(actual, expected)
    assert backend._session is not previous
    assert previous.closed


@gpu
def test_stream_change_clears_old_buffers_on_their_own_stream_before_releasing_capture(monkeypatch):
    model = model_for("llama").cuda()
    backend = graph_class()(model, max_context=32, allow_fixture=True)
    ids = torch.tensor([[3, 5], [7, 11]], device="cuda")
    expected = backend.generate(ids, max_new_tokens=3, eos_token_id=[])
    previous = backend._session
    original = previous.clear
    cleared = []

    def clear_on_owner_stream():
        assert torch.cuda.current_stream(backend.device) == previous.stream
        cleared.append(1)
        return original()

    monkeypatch.setattr(previous, "clear", clear_on_owner_stream)
    other = torch.cuda.Stream()
    with torch.cuda.stream(other):
        actual = backend.generate(ids, max_new_tokens=3, eos_token_id=[])
    other.synchronize()
    assert previous.closed and cleared
    assert backend._session.stream == other
    assert torch.equal(actual, expected)
    backend.release_graph()


@gpu
def test_concurrent_reentry_is_refused_before_prefill(monkeypatch):
    model = model_for("llama").cuda()
    backend = graph_class()(model, max_context=32, allow_fixture=True)
    monkeypatch.setattr(backend, "forward_batch", lambda *a, **kw: pytest.fail("must refuse concurrent reentry"))
    assert backend._call_lock.acquire(blocking=False)
    try:
        with pytest.raises(ReferenceArithmeticError, match="concurrent"):
            backend.generate(torch.tensor([[3, 5]], device="cuda"), max_new_tokens=3)
    finally:
        backend._call_lock.release()


@gpu
def test_captured_arithmetic_error_is_checked_before_output_and_invalidates_graph(monkeypatch):
    model = model_for("llama").cuda()
    backend = graph_class()(model, max_context=32, allow_fixture=True)
    ids = torch.tensor([[3, 5], [7, 11]], device="cuda")
    backend.generate(ids, max_new_tokens=3, eos_token_id=[])
    state = backend._session
    state.drop_capture()
    original = state.decode.store

    def poison(*args, **kwargs):
        result = original(*args, **kwargs)
        if torch.cuda.is_current_stream_capturing():
            state.flag.fill_(1)
        return result

    with monkeypatch.context() as context:
        context.setattr(state.decode, "store", poison)
        with pytest.raises(ReferenceArithmeticError, match="Nonfinite"):
            backend.generate(ids, max_new_tokens=3, eos_token_id=[])
    assert backend._session is None and state.closed
    assert all(not bool(t.any()) for t in state.caches)
    # A rejected result cannot leave a poisoned graph available to the next candidate.
    actual = backend.generate(ids, max_new_tokens=3, eos_token_id=[])
    assert actual.shape == (2, 5)


@gpu
@torch.inference_mode()
def test_captured_kv_bits_and_prefixes_survive_owner_reordering_and_compaction():
    from heteroes.eval import reference_ops as ops
    from heteroes.eval.strict_decoder import StrictDecoderReference

    model = model_for("llama-wide").cuda()
    backend = graph_class()(model, max_context=32, allow_fixture=True)
    oracle = StrictDecoderReference(copy.deepcopy(model).cpu(), max_context=32, allow_fixture=True)
    rows = [torch.tensor([[3, 5]], device="cuda"), torch.tensor([[7, 11, 13, 17]], device="cuda")]
    state = backend._session_for(2)
    try:
        _, prefix = backend.forward_batch(rows)
        state.prefix(prefix, [2, 4])
        state.lengths.copy_(torch.tensor([2, 4], dtype=torch.int32, device="cuda"))
        state.tokens.copy_(torch.tensor([19, 23], device="cuda"))
        inverse = float(ops.reciprocal(torch.tensor(1.0)).item())
        key = state.select([1, 0], 1.0, inverse)
        state.capture(key)
        state.graph.replay()
        state.read()
        histories = [torch.cat((row, torch.tensor([[token]], device="cuda")), 1) for row, token in zip(rows, [19, 23])]
        expected = [oracle.forward_tokens(row.cpu()) for row in histories]
        assert torch.equal(bits(state.last_logits.cpu()), bits(torch.cat([expected[i][0] for i in (1, 0)])))
        for owner, (_, caches) in enumerate(expected):
            for layer, pair in enumerate(caches):
                for kind, tensor in enumerate(pair):
                    start = owner * 32
                    actual = state.caches[2 * layer + kind][:, start : start + histories[owner].shape[1]]
                    assert torch.equal(bits(actual.cpu()), bits(tensor[0]))
        assert state.lengths.tolist() == [3, 5]
        # Only owner zero survives. Its cache remains in its original physical slot.
        state.tokens[0] = 29
        key = state.select([0], 1.0, inverse)
        state.capture(key)
        state.graph.replay()
        state.read()
        final, caches = oracle.forward_tokens(torch.cat((histories[0].cpu(), torch.tensor([[29]])), 1))
        assert torch.equal(bits(state.last_logits.cpu()), bits(final))
        assert state.lengths.tolist() == [4, 5]
        for layer, pair in enumerate(caches):
            for kind, tensor in enumerate(pair):
                assert torch.equal(bits(state.caches[2 * layer + kind][:, :4].cpu()), bits(tensor[0]))
        assert state.capture_count == 2
    finally:
        backend.release_graph()
