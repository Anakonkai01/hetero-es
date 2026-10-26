"""Decode finishes fused with residual add, SiLU gating and RoPE/cache store must equal the unfused kernels."""

import copy
import os

import pytest
import torch

from test_integer_stream import bits, cuda_class, entries_used

# Every fused test shape selects split-K at this CTA target on any GPU size (28..170 SMs).
TARGET = 32

gpu = pytest.mark.skipif(
    os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or not torch.cuda.is_available(), reason="GPU opt-in"
)


def request(kernels, weights):
    kernels._begin_request(list(weights))
    return kernels


def scaled(gen, rows, width, spread=3.0):
    return torch.randn(rows, width, device="cuda", generator=gen) * torch.exp(
        torch.randn(rows, 1, device="cuda", generator=gen) * spread
    )


@gpu
@pytest.mark.parametrize("width,outputs", [(896, 896), (4864, 896), (256, 384), (512, 2048)])
@pytest.mark.parametrize("bias", [False, True])
def test_residual_finish_equals_projection_then_strict_add(width, outputs, bias, monkeypatch):
    kernels = cuda_class()("cuda", magnitude_bits=22)
    used = entries_used(kernels, monkeypatch)
    gen = torch.Generator(device="cuda").manual_seed(width + outputs)
    w = (torch.randn(outputs, width, device="cuda", generator=gen) * 0.03).half()
    b = (torch.randn(outputs, device="cuda", generator=gen) * 0.1).half() if bias else None
    request(kernels, [w])
    for rows in (2, 9, 32):
        x = scaled(gen, rows, width)
        hidden = scaled(gen, rows, outputs, 2.0)
        hidden[0, :3] = torch.tensor([-0.0, 1e-40, -1e-39], device="cuda")
        flags = [kernels.new_error_flag(), kernels.new_error_flag()]
        actual = kernels.linear_decode(x, w, b, error_flag=flags[0], residual=hidden)
        control = kernels.add(hidden, kernels.linear_decode(x, w, b, error_flag=flags[1]), error_flag=flags[1])
        assert int(flags[0].item()) == int(flags[1].item()) == 0
        assert torch.equal(bits(actual), bits(control)), rows
    assert "finish_residual" in used
    # Failures: a nonfinite residual and an overflowing projection report the same bits as the unfused pair.
    for poison in (float("nan"), float("inf")):
        x = scaled(gen, 4, width)
        hidden = scaled(gen, 4, outputs)
        hidden[1, 7] = poison
        flags = [kernels.new_error_flag(), kernels.new_error_flag()]
        actual = kernels.linear_decode(x, w, b, error_flag=flags[0], residual=hidden)
        control = kernels.add(hidden, kernels.linear_decode(x, w, b, error_flag=flags[1]), error_flag=flags[1])
        assert int(flags[0].item()) == int(flags[1].item()) != 0
        assert torch.equal(bits(actual), bits(control))
    huge = torch.full((4, width), 2.0**120, device="cuda")
    flags = [kernels.new_error_flag(), kernels.new_error_flag()]
    actual = kernels.linear_decode(huge, w, b, error_flag=flags[0], residual=hidden)
    control = kernels.add(hidden, kernels.linear_decode(huge, w, b, error_flag=flags[1]), error_flag=flags[1])
    assert int(flags[0].item()) == int(flags[1].item()) != 0
    assert torch.equal(bits(actual), bits(control))
    kernels._end_request()


@gpu
def test_residual_requires_a_matching_tensor_and_single_rows_keep_the_strict_add(monkeypatch):
    from heteroes.eval.reference_ops import ReferenceArithmeticError

    kernels = cuda_class()("cuda", magnitude_bits=22)
    used = entries_used(kernels, monkeypatch)
    w = (torch.randn(384, 256, device="cuda") * 0.03).half()
    request(kernels, [w])
    x = torch.randn(1, 256, device="cuda")
    hidden = torch.randn(1, 384, device="cuda")
    actual = kernels.linear_decode(x, w, residual=hidden)
    assert torch.equal(bits(actual), bits(kernels.add(hidden, kernels.linear_decode(x, w))))
    assert "finish_residual" not in used and "strict_add" in used
    for bad in (hidden[:, :100], hidden.double(), torch.randn(1, 768, device="cuda")[:, ::2]):
        with pytest.raises(ReferenceArithmeticError, match="Residual"):
            kernels.linear_decode(x, w, residual=bad)
    kernels._end_request()


@gpu
@pytest.mark.parametrize("width,n", [(896, 4864), (256, 769), (512, 1024)])
@pytest.mark.parametrize("bias", [False, True])
def test_fused_gate_up_silu_planes_equal_projections_then_silu_quantization(width, n, bias, monkeypatch):
    kernels = cuda_class()("cuda", magnitude_bits=22)
    used = entries_used(kernels, monkeypatch)
    gen = torch.Generator(device="cuda").manual_seed(width * n)
    gate = (torch.randn(n, width, device="cuda", generator=gen) * 0.05).half()
    up = (torch.randn(n, width, device="cuda", generator=gen) * 0.05).half()
    biases = tuple((torch.randn(n, device="cuda", generator=gen) * 0.2).half() for _ in range(2)) if bias else None
    request(kernels, [gate, up])
    for rows in (2, 17, 32):
        x = scaled(gen, rows, width)
        x[0] = 0.0  # zero row: zero maximum, exponent 0
        if rows > 2:
            x[2] *= 1e4  # silu domain: |gate| > 80 on many columns
        prepared = kernels.quantize_input(x, _packed=True)
        flags = [kernels.new_error_flag(), kernels.new_error_flag()]
        planes = kernels.gate_up_silu_quantized(
            prepared, gate, up, biases, error_flag=flags[0], decode_target_ctas_per_sm=TARGET
        )
        assert planes is not None
        g, u = kernels.linear_many(
            None, (gate, up), biases, error_flag=flags[1], decode_target_ctas_per_sm=TARGET, prepared=prepared
        )
        control = kernels.quantize_input(kernels.silu_mul(g, u, error_flag=flags[1]), error_flag=flags[1], _packed=True)
        assert int(flags[0].item()) == int(flags[1].item())
        assert torch.equal(planes[0], control[0]) and torch.equal(planes[1], control[1]), rows
        # The maxima buffer is cleared by every launch: a second identical call gives identical planes.
        again = kernels.gate_up_silu_quantized(prepared, gate, up, biases, decode_target_ctas_per_sm=TARGET)
        assert torch.equal(again[0], planes[0]) and torch.equal(again[1], planes[1])
    assert {"finish_silu", "pack_rows"} <= set(used) and "integer_stream_group" in used
    kernels._end_request()


@gpu
def test_fused_gate_up_reports_nonfinite_and_overflow_like_the_unfused_sequence():
    kernels = cuda_class()("cuda", magnitude_bits=22)
    gen = torch.Generator(device="cuda").manual_seed(3)
    gate = (torch.randn(1024, 512, device="cuda", generator=gen) * 0.05).half()
    up = (torch.randn(1024, 512, device="cuda", generator=gen) * 0.05).half()
    up[5, 0] = 65504.0
    request(kernels, [gate, up])
    for x in (torch.full((4, 512), 2.0**110, device="cuda"), scaled(gen, 4, 512, 8.0)):
        prepared = kernels.quantize_input(x, _packed=True)
        flags = [kernels.new_error_flag(), kernels.new_error_flag()]
        planes = kernels.gate_up_silu_quantized(
            prepared, gate, up, error_flag=flags[0], decode_target_ctas_per_sm=TARGET
        )
        g, u = kernels.linear_many(
            None, (gate, up), error_flag=flags[1], decode_target_ctas_per_sm=TARGET, prepared=prepared
        )
        control = kernels.quantize_input(kernels.silu_mul(g, u, error_flag=flags[1]), error_flag=flags[1], _packed=True)
        assert int(flags[0].item()) == int(flags[1].item())
        assert torch.equal(planes[0], control[0]) and torch.equal(planes[1], control[1])
    kernels._end_request()


@gpu
def test_fused_gate_up_declines_ineligible_inputs():
    kernels = cuda_class()("cuda", magnitude_bits=22)
    gate = (torch.randn(64, 64, device="cuda") * 0.05).half()  # width < 256: one split, no finish to fuse
    request(kernels, [gate])
    prepared = kernels.quantize_input(torch.randn(4, 64, device="cuda"), _packed=True)
    assert kernels.gate_up_silu_quantized(prepared, gate, gate, decode_target_ctas_per_sm=TARGET) is None
    assert kernels.gate_up_silu_quantized(prepared, gate, gate) is None  # no decode plan
    kernels._end_request()
    wide = (torch.randn(64, 512, device="cuda") * 0.05).half()
    other = (torch.randn(32, 512, device="cuda") * 0.05).half()
    request(kernels, [wide, other])
    prepared = kernels.quantize_input(torch.randn(4, 512, device="cuda"), _packed=True)
    assert kernels.gate_up_silu_quantized(prepared, wide, other, decode_target_ctas_per_sm=TARGET) is None
    kernels._end_request()


def _caches(gen, kv, total, dim):
    keys = torch.randn(kv, total, dim, device="cuda", generator=gen)
    return keys, torch.randn(kv, total, dim, device="cuda", generator=gen)


@gpu
@pytest.mark.parametrize("width,heads,kv,dim", [(896, 14, 2, 64), (256, 4, 2, 64), (512, 8, 8, 64), (384, 3, 1, 128)])
@pytest.mark.parametrize("bias", [False, True])
def test_qkv_rope_store_equals_projections_rope_and_cache_store(width, heads, kv, dim, bias, monkeypatch):
    from heteroes.eval import strict_decode_cuda

    kernels = cuda_class()("cuda", magnitude_bits=22)
    decode = strict_decode_cuda.DecodeKernels(kernels)
    used = entries_used(kernels, monkeypatch)
    gen = torch.Generator(device="cuda").manual_seed(width + heads)
    weights = [(torch.randn(n * dim, width, device="cuda", generator=gen) * 0.04).half() for n in (heads, kv, kv)]
    biases = [(torch.randn(w.shape[0], device="cuda", generator=gen) * 0.2).half() for w in weights] if bias else None
    request(kernels, weights)
    total = 40
    for rows in (2, 9, 13):
        x = scaled(gen, rows, width)
        prepared = kernels.quantize_input(x, _packed=True)
        angle = torch.randn(rows, dim, device="cuda", generator=gen) * 3
        cosine, sine = torch.cos(angle), torch.sin(angle)
        cosine[0, 0] = 1e-40  # subnormal table entry is flushed by the strict load
        starts = torch.arange(rows, dtype=torch.int32, device="cuda") * 3  # distinct cache positions
        lengths = torch.randint(1, 4, (rows,), generator=None, dtype=torch.int32).to("cuda")
        ranges = torch.stack((starts, lengths, lengths - 1), 1).to(torch.int32).contiguous()
        keys, values = _caches(gen, kv, total, dim)
        control_keys, control_values = keys.clone(), values.clone()
        flags = [kernels.new_error_flag(), kernels.new_error_flag()]
        q = kernels.qkv_rope_store(
            prepared,
            weights,
            biases,
            cosine,
            sine,
            heads,
            kv,
            ranges,
            keys,
            values,
            error_flag=flags[0],
            decode_target_ctas_per_sm=TARGET,
        )
        assert q is not None
        cq, ck, cv = kernels.linear_many(
            None, weights, biases, error_flag=flags[1], decode_target_ctas_per_sm=TARGET, prepared=prepared
        )
        cq = kernels.rope(cq, cosine, sine, heads, error_flag=flags[1])
        ck = kernels.rope(ck, cosine, sine, kv, error_flag=flags[1])
        decode.store(ck, cv, ranges, control_keys, control_values)
        assert int(flags[0].item()) == int(flags[1].item()) == 0
        assert torch.equal(bits(q), bits(cq)), rows
        assert torch.equal(bits(keys), bits(control_keys)) and torch.equal(bits(values), bits(control_values))
    assert "finish_qkv_rope" in used
    kernels._end_request()


@gpu
def test_qkv_rope_store_reports_failures_and_declines_unsupported_layouts():
    from heteroes.eval import strict_decode_cuda

    kernels = cuda_class()("cuda", magnitude_bits=22)
    decode = strict_decode_cuda.DecodeKernels(kernels)
    gen = torch.Generator(device="cuda").manual_seed(11)
    weights = [(torch.randn(n * 64, 256, device="cuda", generator=gen) * 0.04).half() for n in (4, 2, 2)]
    weights[2][3, 0] = 65504.0
    request(kernels, weights)
    rows, total = 4, 16
    ranges = torch.tensor([[0, 3, 2], [4, 1, 0], [8, 2, 1], [12, 4, 3]], dtype=torch.int32, device="cuda")
    angle = torch.randn(rows, 64, device="cuda", generator=gen)
    cosine, sine = torch.cos(angle), torch.sin(angle)
    sine[2, 5] = float("nan")
    for x in (torch.full((rows, 256), 2.0**118, device="cuda"), scaled(gen, rows, 256)):
        prepared = kernels.quantize_input(x, _packed=True)
        keys, values = _caches(gen, 2, total, 64)
        control_keys, control_values = keys.clone(), values.clone()
        flags = [kernels.new_error_flag(), kernels.new_error_flag()]
        q = kernels.qkv_rope_store(
            prepared,
            weights,
            None,
            cosine,
            sine,
            4,
            2,
            ranges,
            keys,
            values,
            error_flag=flags[0],
            decode_target_ctas_per_sm=TARGET,
        )
        cq, ck, cv = kernels.linear_many(
            None, weights, error_flag=flags[1], decode_target_ctas_per_sm=TARGET, prepared=prepared
        )
        cq = kernels.rope(cq, cosine, sine, 4, error_flag=flags[1])
        ck = kernels.rope(ck, cosine, sine, 2, error_flag=flags[1])
        decode.store(ck, cv, ranges, control_keys, control_values)
        assert int(flags[0].item()) == int(flags[1].item()) != 0
        assert torch.equal(bits(q), bits(cq))
        assert torch.equal(bits(keys), bits(control_keys)) and torch.equal(bits(values), bits(control_values))
    prepared = kernels.quantize_input(scaled(gen, rows, 256), _packed=True)
    keys, values = _caches(gen, 2, total, 64)
    args = (prepared, weights, None, cosine, sine)
    tail = (ranges, keys, values)
    assert kernels.qkv_rope_store(*args, 4, 2, *tail) is None  # no decode plan
    assert kernels.qkv_rope_store(*args, 8, 2, *tail, decode_target_ctas_per_sm=TARGET) is None  # q heads mismatch
    assert kernels.qkv_rope_store(*args, 4, 2, ranges, keys[:1], values[:1], decode_target_ctas_per_sm=TARGET) is None
    assert (
        kernels.qkv_rope_store(
            prepared, weights, None, cosine[:, :32], sine, 4, 2, *tail, decode_target_ctas_per_sm=TARGET
        )
        is None
    )
    assert kernels.qkv_rope_store(*args, 4, 2, ranges.long(), keys, values, decode_target_ctas_per_sm=TARGET) is None
    kernels._end_request()


@gpu
@pytest.mark.parametrize("magnitude_bits", [14, 22])
def test_wide_integer_decoder_with_fused_finishes_matches_cpu_and_unfused_graph(magnitude_bits, monkeypatch):
    from transformers import Qwen2Config, Qwen2ForCausalLM

    from heteroes.eval.integer_decoder import IntegerDecoderGraph, IntegerDecoderReference
    from heteroes.eval.strict_decoder_graph import StrictDecoderGraph

    torch.manual_seed(29)
    cpu = (
        Qwen2ForCausalLM(
            Qwen2Config(
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
        )
        .half()
        .eval()
    )
    with torch.no_grad():
        for layer in cpu.model.layers:
            for norm in (layer.input_layernorm, layer.post_attention_layernorm):
                norm.weight.copy_((0.5 + torch.rand(norm.weight.shape)).half())
        cpu.model.norm.weight.copy_((0.5 + torch.rand(cpu.model.norm.weight.shape)).half())
    ids = torch.tensor([[3, 5, 7, 9], [0, 11, 13, 17], [19, 23, 29, 31], [0, 0, 37, 41]], device="cuda")
    mask = ids != 0
    oracle = IntegerDecoderReference(cpu, max_context=64, allow_fixture=True, magnitude_bits=magnitude_bits)
    expected = oracle.generate(
        ids.cpu(), attention_mask=mask.cpu(), max_new_tokens=5, eos_token_id=[], repetition_penalty=1.2
    )
    model = copy.deepcopy(cpu).cuda()
    fused = IntegerDecoderGraph(model, max_context=64, allow_fixture=True, magnitude_bits=magnitude_bits)
    used = entries_used(fused.kernels, monkeypatch)
    actual = fused.generate(ids, attention_mask=mask, max_new_tokens=5, eos_token_id=[], repetition_penalty=1.2)
    assert torch.equal(actual.cpu(), expected)
    logits = fused._session.last_logits.clone()
    assert {"finish_qkv_rope", "finish_silu", "pack_rows", "finish_residual"} <= set(used)
    fused.release_graph()
    # The base composition (rope, store, silu and add kernels) gives the same logits bit for bit.
    for name in ("_decode_attention_input", "_decode_residual_project", "_decode_mlp"):
        monkeypatch.setattr(IntegerDecoderGraph, name, getattr(StrictDecoderGraph, name))
    unfused = IntegerDecoderGraph(model, max_context=64, allow_fixture=True, magnitude_bits=magnitude_bits)
    assert torch.equal(
        unfused.generate(ids, attention_mask=mask, max_new_tokens=5, eos_token_id=[], repetition_penalty=1.2), actual
    )
    assert torch.equal(bits(unfused._session.last_logits), bits(logits))
    unfused.release_graph()
