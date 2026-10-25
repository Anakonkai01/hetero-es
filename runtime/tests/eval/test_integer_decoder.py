"""New integer-linear graph composition must match its own independent CPU oracle and isolate candidates."""

import copy
import os

import pytest
import torch

from heteroes.eval.reference_ops import ReferenceArithmeticError
from test_strict_decoder import model_for, bits


def classes():
    from heteroes.eval.integer_decoder import IntegerDecoderReference, IntegerDecoderGraph

    return IntegerDecoderReference, IntegerDecoderGraph


@pytest.mark.parametrize("magnitude_bits", [14, 22])
def test_integer_graph_has_separate_arithmetic_namespace_and_cpu_reference(magnitude_bits):
    reference, graph = classes()
    model = model_for("llama-wide")
    backend = reference(model, max_context=32, allow_fixture=True, magnitude_bits=magnitude_bits)
    ids = torch.tensor([[3, 5, 7]])
    expected, cache = backend.forward_tokens(ids)
    _, prefix = backend.forward_tokens(ids[:, :2])
    actual, _ = backend.forward_tokens(ids[:, 2:], prefix)
    assert torch.equal(bits(actual), bits(expected))
    assert backend.identity["backend"] == "decoder_scaled_integer_reference_v1_experimental"
    assert backend.identity["operators"]["linear"]["magnitudeBits"] == magnitude_bits
    assert backend.identity["hardwareQualified"] is False
    assert backend.generate(ids, max_new_tokens=3, eos_token_id=[]).shape == (1, 6)


def test_integer_decoder_precision_and_cuda_guards():
    reference, graph = classes()
    model = model_for("llama")
    for backend in (reference, graph):
        with pytest.raises(ReferenceArithmeticError, match="magnitude"):
            backend(model, magnitude_bits=True)
    with pytest.raises(ReferenceArithmeticError):
        graph(model)


gpu = pytest.mark.skipif(
    os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or not torch.cuda.is_available(), reason="GPU opt-in"
)


@gpu
@pytest.mark.parametrize("family", ["qwen2", "llama", "llama-wide", "mistral"])
@pytest.mark.parametrize("magnitude_bits", [14, 22])
def test_integer_captured_graph_matches_cpu_logits_tokens_and_live_changed_weights(family, magnitude_bits):
    reference, graph = classes()
    cpu = model_for(family)
    model = copy.deepcopy(cpu).cuda()
    backend = graph(model, max_context=32, allow_fixture=True, magnitude_bits=magnitude_bits)
    oracle = reference(cpu, max_context=32, allow_fixture=True, magnitude_bits=magnitude_bits)
    ids = torch.tensor([[0, 3, 5], [7, 11, 13], [0, 17, 19]], device="cuda")
    mask = ids != 0
    snapshot = cpu.model.layers[0].mlp.down_proj.weight.detach().clone()
    session = None
    parents = []
    for factor in (1.0, -16.0, 1.0):
        with torch.no_grad():
            cpu.model.layers[0].mlp.down_proj.weight.copy_(snapshot * factor)
            model.model.layers[0].mlp.down_proj.weight.copy_((snapshot * factor).cuda())
        expected = oracle.generate(
            ids.cpu(), attention_mask=mask.cpu(), max_new_tokens=4, eos_token_id=[], repetition_penalty=1.2
        )
        actual = backend.generate(ids, attention_mask=mask, max_new_tokens=4, eos_token_id=[], repetition_penalty=1.2)
        assert torch.equal(actual.cpu(), expected)
        parents.append(actual.clone())
        if session is None:
            session = backend._session
        assert session is backend._session and session.capture_count == 1
        fed = [torch.cat((row[allowed], out[ids.shape[1] : -1]))[None] for row, allowed, out in zip(ids, mask, actual)]
        logits = torch.cat([oracle.forward_tokens(row.cpu())[0] for row in fed])
        assert torch.equal(bits(session.last_logits.cpu()), bits(logits))
        assert all(not bool(t.any()) for t in session.caches)
    assert torch.equal(parents[0], parents[2])
    assert backend.identity["backend"] == "decoder_scaled_integer_cuda_graph_v1_experimental"
    assert backend.identity["operators"]["linear"]["magnitudeBits"] == magnitude_bits
    backend.release_graph()


@gpu
def test_metadata_refreshes_once_per_request_and_is_cleared_under_generation_lock(monkeypatch):
    _, graph = classes()
    model = model_for("llama").cuda()
    backend = graph(model, max_context=32, allow_fixture=True)
    kernels = backend.kernels
    calls = []
    refresh = kernels._refresh_weight_exponents

    def counted(weight, exponents, flag):
        assert backend._call_lock.locked()
        calls.append(weight.data_ptr())
        return refresh(weight, exponents, flag)

    monkeypatch.setattr(kernels, "_refresh_weight_exponents", counted)
    ids = torch.tensor([[3, 5, 7], [11, 13, 17]], device="cuda")
    weight = model.model.layers[0].mlp.down_proj.weight
    saved = weight.detach().clone()
    parent = backend.generate(ids, max_new_tokens=4, eos_token_id=[])
    unique = len(set(calls))
    assert len(calls) == unique and unique == 7 * model.config.num_hidden_layers + 1
    buffers = tuple(kernels.weight_metadata_buffers())
    assert buffers and all(not bool(t.any()) for t in buffers)
    pointers = [t.data_ptr() for t in buffers]
    assert not kernels._request_active
    with torch.no_grad():
        weight.copy_(saved * -32)
    backend.generate(ids, max_new_tokens=4, eos_token_id=[])
    assert len(calls) == 2 * unique
    assert [t.data_ptr() for t in kernels.weight_metadata_buffers()] == pointers
    assert backend._session.capture_count == 1
    with torch.no_grad():
        weight.copy_(saved)
    assert torch.equal(parent, backend.generate(ids, max_new_tokens=4, eos_token_id=[]))
    assert len(calls) == 3 * unique

    # Ordinary forward outside a request must recompute rather than reading cleared request metadata.
    def outside_request(weight, exponents, flag):
        assert not backend._call_lock.locked()
        calls.append(weight.data_ptr())
        return refresh(weight, exponents, flag)

    monkeypatch.setattr(kernels, "_refresh_weight_exponents", outside_request)
    backend.forward_batch([row[None] for row in ids])
    assert len(calls) > 3 * unique
    assert not backend._call_lock.locked()


@gpu
def test_metadata_invalidates_on_rebind_and_nonfinite_request_does_not_poison_next_request():
    reference, graph = classes()
    cpu = model_for("llama")
    model = copy.deepcopy(cpu).cuda()
    backend = graph(model, max_context=32, allow_fixture=True)
    ids = torch.tensor([[3, 5, 7]], device="cuda")
    expected = reference(cpu, max_context=32, allow_fixture=True).generate(ids.cpu(), max_new_tokens=3, eos_token_id=[])
    assert torch.equal(backend.generate(ids, max_new_tokens=3, eos_token_id=[]).cpu(), expected)
    old = backend._session
    module = model.model.layers[0].mlp.down_proj
    module.weight = torch.nn.Parameter(module.weight.detach().clone())
    assert torch.equal(backend.generate(ids, max_new_tokens=3, eos_token_id=[]).cpu(), expected)
    assert old.closed and backend._session is not old
    with torch.no_grad():
        module.weight[0, 0] = float("nan")
    with pytest.raises(ReferenceArithmeticError, match="Nonfinite"):
        backend.generate(ids, max_new_tokens=3, eos_token_id=[])
    assert not backend._call_lock.locked() and not backend.kernels._request_active
    assert backend._session is None
    assert all(not bool(t.any()) for t in backend.kernels.weight_metadata_buffers())
    with torch.no_grad():
        module.weight.copy_(cpu.model.layers[0].mlp.down_proj.weight.cuda())
    assert torch.equal(backend.generate(ids, max_new_tokens=3, eos_token_id=[]).cpu(), expected)
    # The same refresh lifetime applies to the uncaptured generation path.
    assert torch.equal(backend.generate(ids, max_new_tokens=3, eos_token_id=[], use_cache=False).cpu(), expected)
    assert not backend.kernels._request_active
