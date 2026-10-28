"""Packed multi-sequence kernels must preserve every sequence's independent reference computation."""

import copy
import os

import pytest
import torch

from heteroes.strict import strict_cuda
from heteroes.strict.qwen2_reference import Qwen2Reference
from heteroes.strict.reference_ops import ReferenceArithmeticError
from test_qwen2_strict_cuda import bits, make_model
from test_strict_cuda import _reference_attention

gpu = pytest.mark.skipif(
    os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or not torch.cuda.is_available(),
    reason="packed strict checks need explicit GPU acceptance",
)


def packed_class():
    from heteroes.strict.strict_decoder_packed import StrictDecoderPacked

    return StrictDecoderPacked


@pytest.mark.parametrize("spans", [[], [(0, 1, 1)], [(1, -1, 0)], [(1, 2, 0)], [(True, 1, 0)], [(1, 4097, 4096)]])
def test_packed_attention_refuses_invalid_spans_before_launch(spans):
    kernels = object.__new__(strict_cuda.StrictCudaKernels)
    kernels.device = torch.device("cpu")
    with pytest.raises(ReferenceArithmeticError, match="[Ss]pan"):
        kernels.attention_packed(torch.ones(2, 1, 4), torch.ones(1, 1, 4), torch.ones(1, 1, 4), spans, 2, 0.5)


@pytest.mark.parametrize(
    "options",
    [
        {"do_sample": True},
        {"num_beams": 2},
        {"max_new_tokens": 65},
        {"repetition_penalty": float("inf")},
        {"eos_token_id": [43]},
        {"unknown": True},
    ],
)
def test_packed_generation_refuses_unsupported_requests_before_computation(options, monkeypatch):
    backend = object.__new__(packed_class())
    model = make_model()
    backend.config, backend.generation_config, backend.device = (
        model.config,
        model.generation_config,
        torch.device("cpu"),
    )
    backend.max_context = 64
    monkeypatch.setattr(backend, "forward_batch", lambda *a, **kw: pytest.fail("must refuse before computation"))
    with pytest.raises(ReferenceArithmeticError):
        backend.generate(torch.tensor([[2, 5]]), **options)


@gpu
@pytest.mark.parametrize("spans", [[(3, 3, 0), (1, 8, 7), (2, 5, 3)], [(1, 1, 0), (1, 257, 256)]])
def test_packed_attention_matches_independent_cpu_trees_and_permutation(spans):
    kernels = strict_cuda.StrictCudaKernels("cuda")
    gen = torch.Generator().manual_seed(37)
    qs, ks, vs, expected = [], [], [], []
    for length, keys, past in spans:
        q = torch.randn(4, length, 8, generator=gen)
        k = torch.randn(2, keys, 8, generator=gen)
        v = torch.randn(2, keys, 8, generator=gen)
        qs.append(q.cuda())
        ks.append(k.cuda())
        vs.append(v.cuda())
        expected.append(_reference_attention(q, k, v, past, 2, 0.5))
    for order in (list(range(len(spans))), list(reversed(range(len(spans))))):
        actual = kernels.attention_packed(
            torch.cat([qs[i] for i in order], 1),
            torch.cat([ks[i] for i in order], 1),
            torch.cat([vs[i] for i in order], 1),
            [spans[i] for i in order],
            2,
            0.5,
        )
        assert torch.equal(bits(actual.cpu()), bits(torch.cat([expected[i] for i in order])))
    vs[-1][-1, -1, -1] = float("inf")
    with pytest.raises(ReferenceArithmeticError, match="Nonfinite"):
        kernels.attention_packed(torch.cat(qs, 1), torch.cat(ks, 1), torch.cat(vs, 1), spans, 2, 0.5)


@gpu
def test_packed_graph_ragged_prefill_decode_permutation_and_compaction():
    model = make_model().cuda()
    packed = packed_class()(model, max_context=64, allow_fixture=True)
    cpu = Qwen2Reference(copy.deepcopy(model).cpu(), max_context=64, allow_fixture=True)
    rows = [torch.tensor([tokens], device="cuda") for tokens in ([2, 5, 7], [3], [11, 13, 17, 19, 23])]
    expected = [cpu.forward_tokens(row.cpu()) for row in rows]
    actual, caches = packed.forward_batch(rows)
    assert torch.equal(bits(actual.cpu()), bits(torch.cat([r[0] for r in expected])))
    for cache, (_, oracle) in zip(caches, expected):
        for (k, v), (ek, ev) in zip(cache, oracle):
            assert torch.equal(bits(k.cpu()), bits(ek)) and torch.equal(bits(v.cpu()), bits(ev))
    # Drop a finished row and reorder survivors while carrying only their own cache.
    order = [2, 0]
    more = [torch.tensor([[29]], device="cuda"), torch.tensor([[31, 37]], device="cuda")]
    actual, _ = packed.forward_batch(more, [caches[i] for i in order])
    oracle = [cpu.forward_tokens(torch.cat((rows[i].cpu(), tail.cpu()), 1))[0] for i, tail in zip(order, more)]
    assert torch.equal(bits(actual.cpu()), bits(torch.cat(oracle)))


@gpu
def test_decode_concatenation_count_is_bounded_by_layers_not_sequences(monkeypatch):
    model = make_model().cuda()
    packed = packed_class()(model, max_context=64, allow_fixture=True)
    rows = [torch.tensor([[2, 5, 7]], device="cuda") for _ in range(8)]
    _, caches = packed.forward_batch(rows)
    original, calls = torch.cat, []

    def counted(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(torch, "cat", counted)
        actual, _ = packed.forward_batch([row[:, -1:] for row in rows], caches)
    assert len(calls) <= 1 + 2 * model.config.num_hidden_layers
    expected = Qwen2Reference(model, max_context=64, allow_fixture=True).forward_tokens(
        torch.tensor([[2, 5, 7, 7]], device="cuda")
    )[0]
    assert torch.equal(bits(actual), bits(expected.expand_as(actual)))


@gpu
@pytest.mark.parametrize("options", [{}, {"repetition_penalty": 1.3}, {"use_cache": False}, {"eos_token_id": [9, 17]}])
def test_packed_generate_matches_serial_with_padding_and_candidate_changes(options):
    model = make_model().cuda()
    packed = packed_class()(model, max_context=64, allow_fixture=True)
    eager = Qwen2Reference(model, max_context=64, allow_fixture=True)
    ids = torch.tensor([[0, 0, 2, 5], [7, 11, 13, 17], [0, 3, 3, 3]], device="cuda")
    mask = ids != 0
    snapshot = model.model.layers[0].mlp.down_proj.weight.detach().clone()
    for factor in (1.0, -1.0, 1.0):
        with torch.no_grad():
            model.model.layers[0].mlp.down_proj.weight.copy_(snapshot * factor)
        actual = packed.generate(ids, attention_mask=mask, max_new_tokens=6, **options)
        expected = eager.generate(ids, attention_mask=mask, max_new_tokens=6, **options)
        assert torch.equal(actual, expected)


@gpu
def test_packed_generation_compacts_eos_rows_and_uses_no_hf_or_weight_copy(monkeypatch):
    model = make_model().cuda()
    packed = packed_class()(model, max_context=64, allow_fixture=True)
    ids = torch.tensor([[2, 5], [7, 11], [13, 17]], device="cuda")
    # Scripted logits test compaction and explicit ties independently from random-model behavior.
    calls = []

    def scripted(rows, caches=None):
        calls.append(len(rows))
        if len(calls) == 2:
            assert caches == [("cache", 1), ("cache", 2)]
        scores = torch.zeros((len(rows), 41), device="cuda")
        if len(calls) == 1:
            scores[0, 40] = 2.0
            scores[1:, 9] = 2.0
        else:
            scores[:, 40] = 2.0
        return scores, [("cache", i) for i in range(len(rows))]

    monkeypatch.setattr(packed, "forward_batch", scripted)
    result = packed.generate(ids, max_new_tokens=5, pad_token_id=1)
    assert result[:, 2:].tolist() == [[40, 1], [9, 40], [9, 40]]
    assert calls == [3, 2]
