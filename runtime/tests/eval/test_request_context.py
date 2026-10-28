"""KV slots sized to the request: same tokens/logits as the CPU oracle; configured limits and admission unchanged."""

import os
import threading

import pytest
import torch

from heteroes.strict.reference_ops import ReferenceArithmeticError
from heteroes.strict.strict_decoder_graph import request_context
from test_strict_decoder import bits, model_for


@pytest.mark.parametrize(
    "lengths, new, expected",
    [([3], 3, 16), ([3, 13], 3, 16), ([3, 14], 3, 32), ([17], 15, 32), ([500], 12, 512), ([1], 1, 16)],
)
def test_physical_context_is_the_request_budget_rounded_up_to_16_within_the_limit(lengths, new, expected):
    assert request_context(512, lengths, new) == expected


def test_request_context_never_exceeds_the_configured_limit():
    assert request_context(40, [30], 9) == 40
    assert request_context(40, [30], 10) == 40  # admission (prompt + new <= limit) is checked before, unchanged


gpu = pytest.mark.skipif(
    os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or not torch.cuda.is_available(), reason="GPU opt-in"
)


def engines(**options):
    from heteroes.strict.integer_decoder import IntegerDecoderGraph, IntegerDecoderReference

    cpu = model_for("llama")
    model = model_for("llama").cuda()
    oracle = IntegerDecoderReference(cpu, allow_fixture=True, max_context=64, magnitude_bits=22)
    engine = IntegerDecoderGraph(model, allow_fixture=True, max_context=64, magnitude_bits=22, **options)
    return cpu, model, oracle, engine


SMALL = torch.tensor([[3, 5, 7], [11, 13, 17]])
LARGE = torch.tensor([[3, 5, 7] * 5 + [11, 13], [17, 19, 23] * 5 + [29, 31]])


@gpu
def test_context_changes_keep_cpu_logits_tokens_restore_and_clearing():
    cpu, model, oracle, engine = engines()
    saved = cpu.model.layers[0].mlp.down_proj.weight.detach().clone()
    for ids, factor, context in ((SMALL, 1.0, 16), (LARGE, -16.0, 32), (SMALL, 1.0, 16)):
        with torch.no_grad():
            cpu.model.layers[0].mlp.down_proj.weight.copy_(saved * factor)
            model.model.layers[0].mlp.down_proj.weight.copy_((saved * factor).cuda())
        expected = oracle.generate(ids, max_new_tokens=3, eos_token_id=[])
        actual = engine.generate(ids.cuda(), max_new_tokens=3, eos_token_id=[])
        assert torch.equal(actual.cpu(), expected)
        logits, _ = oracle.forward_tokens(expected[0, :-1][None])
        assert torch.equal(bits(engine._session.last_logits[0].cpu()), bits(logits[0]))
        assert engine.max_context == 64 and engine._session.context == context
        assert all(t.shape[1] == 2 * context and not bool(t.any()) for t in engine._session.caches)
    state = engine._session
    engine.generate(SMALL.cuda(), max_new_tokens=3, eos_token_id=[])
    assert engine._session is state and state.capture_count == 1  # same bucket: the capture is reused


@gpu
def test_eos_inside_a_small_bucket_matches_the_oracle():
    cpu, model, oracle, engine = engines()
    probe = oracle.generate(SMALL, max_new_tokens=6, eos_token_id=[])
    eos = int(probe[0, SMALL.shape[1] + 1])  # the first row stops after two tokens
    expected = oracle.generate(SMALL, max_new_tokens=6, eos_token_id=[eos], pad_token_id=0)
    actual = engine.generate(SMALL.cuda(), max_new_tokens=6, eos_token_id=[eos], pad_token_id=0)
    assert torch.equal(actual.cpu(), expected) and engine._session.context == 16


@gpu
def test_configured_context_and_conservative_budget_still_reject():
    model = model_for("llama").cuda()
    from heteroes.strict.integer_decoder import IntegerDecoderGraph

    engine = IntegerDecoderGraph(model, allow_fixture=True, max_context=64, magnitude_bits=22, max_graph_bytes=1)
    with pytest.raises(ReferenceArithmeticError, match="memory budget"):
        engine.generate(SMALL.cuda(), max_new_tokens=3, eos_token_id=[])
    assert engine._session is None
    with pytest.raises(ReferenceArithmeticError, match="context limit"):
        engine.generate(SMALL.cuda(), max_new_tokens=64, eos_token_id=[])


@gpu
def test_parameter_replacement_and_failure_release_the_bucket_session():
    cpu, model, oracle, engine = engines()
    engine.generate(SMALL.cuda(), max_new_tokens=3, eos_token_id=[])
    first = engine._session
    layer = model.model.layers[0].mlp.down_proj
    layer.weight = torch.nn.Parameter(layer.weight.detach().clone())  # rebinding: new pointer
    assert torch.equal(
        engine.generate(SMALL.cuda(), max_new_tokens=3, eos_token_id=[]).cpu(),
        oracle.generate(SMALL, max_new_tokens=3, eos_token_id=[]),
    )
    assert engine._session is not first
    saved = layer.weight.detach().clone()
    with torch.no_grad():
        layer.weight[0, 0] = float("inf")
    with pytest.raises(ReferenceArithmeticError):
        engine.generate(LARGE.cuda(), max_new_tokens=3, eos_token_id=[])
    assert engine._session is None  # a failed request releases its capture
    with torch.no_grad():
        layer.weight.copy_(saved)
    assert torch.equal(
        engine.generate(LARGE.cuda(), max_new_tokens=3, eos_token_id=[]).cpu(),
        oracle.generate(LARGE, max_new_tokens=3, eos_token_id=[]),
    )
    assert engine._session.context == 32


@gpu
def test_concurrent_requests_are_refused_before_touching_the_context():
    cpu, model, oracle, engine = engines()
    engine.generate(SMALL.cuda(), max_new_tokens=3, eos_token_id=[])
    entered, release = threading.Event(), threading.Event()
    begin = engine._generation_begin

    def blocking():
        entered.set()
        release.wait(30)
        return begin()

    engine._generation_begin = blocking
    worker = threading.Thread(target=lambda: engine.generate(LARGE.cuda(), max_new_tokens=3, eos_token_id=[]))
    worker.start()
    assert entered.wait(30)
    context = engine._session.context
    with pytest.raises(ReferenceArithmeticError, match="concurrent"):
        engine.generate(SMALL.cuda(), max_new_tokens=3, eos_token_id=[])
    assert engine._session.context == context
    release.set()
    worker.join(60)
    del engine._generation_begin
    assert engine._session.context == 32
