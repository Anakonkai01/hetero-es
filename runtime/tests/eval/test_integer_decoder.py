"""New integer-linear graph composition must match its own independent CPU oracle and isolate candidates."""

import copy
import os

import pytest
import torch

from heteroes.strict.reference_ops import ReferenceArithmeticError
from test_strict_decoder import model_for, bits


def classes():
    from heteroes.strict.integer_decoder import IntegerDecoderReference, IntegerDecoderGraph

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
    for target in (True, -1, 65, 1.5):
        with pytest.raises(ReferenceArithmeticError, match="target"):
            graph(model, decode_target_ctas_per_sm=target)


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
    refresh, batched = kernels._refresh_weight_exponents, kernels._refresh_exponents_batched

    def counted(weight, exponents, flag):
        assert backend._call_lock.locked()
        calls.append(weight.data_ptr())
        return refresh(weight, exponents, flag)

    def counted_batch(entries, flag):
        assert backend._call_lock.locked()
        calls.extend(weight.data_ptr() for weight, _ in entries)
        return batched(entries, flag)

    monkeypatch.setattr(kernels, "_refresh_weight_exponents", counted)
    monkeypatch.setattr(kernels, "_refresh_exponents_batched", counted_batch)
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


@gpu
def test_decode_policy_uses_split_partials_matches_cpu_and_keeps_live_restore(monkeypatch):
    from transformers import LlamaConfig, LlamaForCausalLM

    reference, graph = classes()
    torch.manual_seed(193)
    cpu = (
        LlamaForCausalLM(
            LlamaConfig(
                hidden_size=64,
                intermediate_size=769,
                num_attention_heads=8,
                num_key_value_heads=2,
                num_hidden_layers=1,
                vocab_size=67,
                max_position_embeddings=64,
                eos_token_id=66,
                pad_token_id=0,
            )
        )
        .half()
        .eval()
    )
    model = copy.deepcopy(cpu).cuda()
    backend = graph(model, max_context=64, allow_fixture=True, decode_target_ctas_per_sm=8)
    oracle = reference(cpu, max_context=64, allow_fixture=True)
    ids = torch.tensor([[3, 5, 7], [11, 13, 17], [19, 23, 29]], device="cuda")
    calls = []
    linear = backend.kernels._linear

    def observed(value, weight, bias=None, **kwargs):
        calls.append((weight.shape[1], kwargs.get("split_k", 1)))
        return linear(value, weight, bias, **kwargs)

    monkeypatch.setattr(backend.kernels, "_linear", observed)
    saved = cpu.model.layers[0].mlp.down_proj.weight.detach().clone()
    parents = []
    for factor in (1.0, -16.0, 1.0):
        with torch.no_grad():
            cpu.model.layers[0].mlp.down_proj.weight.copy_(saved * factor)
            model.model.layers[0].mlp.down_proj.weight.copy_((saved * factor).cuda())
        expected = oracle.generate(ids.cpu(), max_new_tokens=4, eos_token_id=[])
        actual = backend.generate(ids, max_new_tokens=4, eos_token_id=[])
        assert torch.equal(actual.cpu(), expected)
        parents.append(actual.clone())
        assert backend._session.capture_count == 1
    assert torch.equal(parents[0], parents[2])
    assert any(width == 769 and split == 8 for width, split in calls)
    assert backend.identity["decodeExecution"]["targetCtasPerSm"] == 8
    assert backend._request_workspace_bytes(3) > sum(t.numel() * 4 for t in backend.kernels.weight_metadata_buffers())
    with pytest.raises(AttributeError):
        backend.decode_target_ctas_per_sm = 0
    budget = backend.kernels.max_partial_bytes
    backend.kernels.max_partial_bytes = 1
    with pytest.raises(ReferenceArithmeticError, match="configuration"):
        backend.generate(ids, max_new_tokens=4, eos_token_id=[])
    assert backend._session is None and not backend._call_lock.locked()
    backend.kernels.max_partial_bytes = budget
    assert torch.equal(parents[0], backend.generate(ids, max_new_tokens=4, eos_token_id=[]))
    previous_load = backend.kernels.weight_load
    backend.kernels.weight_load = "scalar" if previous_load != "scalar" else "paired"
    with pytest.raises(ReferenceArithmeticError, match="configuration"):
        backend.generate(ids, max_new_tokens=4, eos_token_id=[])
    assert backend._session is None and not backend._call_lock.locked()
    backend.kernels.weight_load = previous_load
    assert torch.equal(parents[0], backend.generate(ids, max_new_tokens=4, eos_token_id=[]))


@gpu
def test_decode_partial_budget_is_admitted_before_request_cache_or_metadata_allocations(monkeypatch):
    import heteroes.strict.strict_decoder_graph as graph_module

    _, graph = classes()
    backend = graph(model_for("llama").cuda(), max_context=32, allow_fixture=True)
    # A deterministic synthetic extra bound isolates the generation admission path without a large model.
    monkeypatch.setattr(backend, "_request_workspace_bytes", lambda capacity=1: 1024)
    monkeypatch.setattr(graph_module, "graph_memory_bound", lambda *args, **kwargs: 0)
    backend.max_graph_bytes = 1023
    monkeypatch.setattr(backend, "_session_for", lambda *args: pytest.fail("budget must precede cache allocation"))
    monkeypatch.setattr(backend, "_generation_begin", lambda: pytest.fail("budget must precede metadata refresh"))
    with pytest.raises(ReferenceArithmeticError, match="budget"):
        backend.generate(torch.tensor([[3, 5]], device="cuda"), max_new_tokens=3, eos_token_id=[])


@gpu
@pytest.mark.parametrize("magnitude_bits", [14, 22])
def test_wide_decoder_with_split_groups_and_distinct_norms_matches_cpu(magnitude_bits, monkeypatch):
    # Hidden 256 selects split-K grouped projections and fused norm/SiLU quantization; distinct RMSNorm weights
    # (the fixtures default to ones) make every norm-to-projection pairing observable.
    from transformers import Qwen2Config, Qwen2ForCausalLM

    from heteroes.strict import integer_plan
    from test_integer_stream import entries_used

    reference, graph = classes()
    torch.manual_seed(31)
    config = Qwen2Config(
        hidden_size=256,
        intermediate_size=769,
        num_attention_heads=4,
        num_key_value_heads=2,
        num_hidden_layers=2,
        vocab_size=91,
        max_position_embeddings=64,
        eos_token_id=90,
        pad_token_id=0,
    )
    cpu = Qwen2ForCausalLM(config).half().eval()
    with torch.no_grad():
        norms = [cpu.model.norm] + [
            n for layer in cpu.model.layers for n in (layer.input_layernorm, layer.post_attention_layernorm)
        ]
        for norm in norms:
            norm.weight.copy_((0.5 + torch.rand(norm.weight.shape)).half())
    oracle = reference(cpu, max_context=64, allow_fixture=True, magnitude_bits=magnitude_bits)
    backend = graph(copy.deepcopy(cpu).cuda(), max_context=64, allow_fixture=True, magnitude_bits=magnitude_bits)
    used = entries_used(backend.kernels, monkeypatch)
    ids = torch.tensor([[3, 5, 7, 9], [0, 11, 13, 17], [19, 23, 29, 31], [0, 0, 37, 41]], device="cuda")
    mask = ids != 0
    expected = oracle.generate(
        ids.cpu(), attention_mask=mask.cpu(), max_new_tokens=5, eos_token_id=[], repetition_penalty=1.2
    )
    actual = backend.generate(ids, attention_mask=mask, max_new_tokens=5, eos_token_id=[], repetition_penalty=1.2)
    assert torch.equal(actual.cpu(), expected)
    fed = [torch.cat((row[allowed], out[ids.shape[1] : -1]))[None] for row, allowed, out in zip(ids, mask, actual)]
    logits = torch.cat([oracle.forward_tokens(row.cpu())[0] for row in fed])
    assert torch.equal(bits(backend._session.last_logits.cpu()), bits(logits))
    assert {
        "integer_stream_group",
        "strict_rms_quant",
        "finish_qkv_rope",
        "finish_silu",
        "pack_rows",
        "finish_residual",
    } <= set(used)
    # The workspace bound is a no-reuse sum: it covers every single-matrix partial plus every grouped partial.
    multiprocessors, budget = backend.kernels.multiprocessors, backend.kernels.max_partial_bytes
    for capacity in (1, 4):
        needed = 0
        layers = backend.model.model.layers
        for layer in layers:
            attention, mlp = layer.self_attn, layer.mlp
            singles = [
                attention.q_proj,
                attention.k_proj,
                attention.v_proj,
                attention.o_proj,
                mlp.gate_proj,
                mlp.up_proj,
                mlp.down_proj,
            ]
            groups = [(attention.q_proj, attention.k_proj, attention.v_proj), (mlp.gate_proj, mlp.up_proj)]
            for width, outputs in [(m.weight.shape[1], m.weight.shape[0]) for m in singles] + [
                (g[0].weight.shape[1], sum(m.weight.shape[0] for m in g)) for g in groups
            ]:
                needed += max(
                    integer_plan.decode_linear_plan(
                        width, rows, outputs, multiprocessors, max_partial_bytes=budget
                    ).partial_bytes
                    for rows in range(1, capacity + 1)
                )
        assert backend._request_workspace_bytes(capacity) >= needed
    backend.release_graph()


@gpu
def test_generation_accepts_only_nonempty_left_padded_prompts_and_takes_their_suffix():
    _, graph = classes()
    backend = graph(model_for("llama").cuda(), max_context=16, allow_fixture=True)
    ids = torch.tensor([[3, 5, 7, 9], [0, 0, 11, 13], [0, 17, 19, 23]], device="cuda")
    mask = torch.tensor([[1, 1, 1, 1], [0, 0, 1, 1], [0, 1, 1, 1]], device="cuda")
    histories, *_ = backend._prepare_generation(ids, mask, max_new_tokens=2, eos_token_id=[])
    assert [h.tolist() for h in histories] == [[[3, 5, 7, 9]], [[11, 13]], [[17, 19, 23]]]
    for bad in ([1, 0, 1, 1], [0, 0, 0, 0], [1, 1, 0, 0], [0, 1, 0, 1]):
        broken = mask.clone()
        broken[1] = torch.tensor(bad, device="cuda")
        with pytest.raises(ReferenceArithmeticError, match="left-padded"):
            backend._prepare_generation(ids, broken, max_new_tokens=2, eos_token_id=[])
    with pytest.raises(ReferenceArithmeticError, match="context"):
        backend._prepare_generation(ids, mask, max_new_tokens=13, eos_token_id=[])
    backend._prepare_generation(ids, mask, max_new_tokens=12, eos_token_id=[])
