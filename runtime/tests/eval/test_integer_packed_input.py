"""Packed radix planes retain exact q, zero tails and admitted memory on narrow graphs."""

import copy
import os

import pytest
import torch

from heteroes.eval.integer_cuda import IntegerCudaKernels
from heteroes.eval.integer_reference import quantize_rows
from heteroes.eval.reference_ops import ReferenceArithmeticError

gpu = pytest.mark.skipif(
    os.environ.get("HETEROES_GPU_ACCEPTANCE") != "1" or not torch.cuda.is_available(), reason="GPU opt-in"
)


@gpu
@pytest.mark.parametrize("bits", [14, 22])
@pytest.mark.parametrize("width", [1, 3, 4, 31, 33, 67, 257, 32768])
def test_packed_planes_reconstruct_quantized_rows_and_zero_padding(bits, width):
    generator = torch.Generator().manual_seed(width + bits)
    value = torch.randn(5, width, generator=generator)
    value[1] = -0.0
    value[2] = torch.tensor(1, dtype=torch.int32).view(torch.float32)
    carries = torch.tensor(
        [0, 1, -1, 127, 128, 129, -127, -128, -129, 32767, 32768, 32769, -32767, -32768, -32769, 2**bits - 1],
        dtype=torch.float32,
    ) / 2 ** (bits - 1)
    value[3, : min(width, len(carries))] = carries[:width]
    value[4] = 1.9999998807907104
    expected, exponents = quantize_rows(value, magnitude_bits=bits)
    kernels = IntegerCudaKernels("cuda", magnitude_bits=bits)
    packed, actual_exponents = kernels.quantize_input(value.cuda(), _packed=True)
    digits, words = 2 if bits == 14 else 3, (width + 3) // 4
    assert packed.shape == (digits, 5, words) and packed.dtype == torch.int32
    raw = packed.cpu().to(torch.int64) & 0xFFFFFFFF
    reconstructed = torch.zeros((5, words, 4), dtype=torch.int64)
    for degree in range(digits):
        byte = (raw[degree, :, :, None] >> torch.tensor([0, 8, 16, 24])) & 255
        digit = torch.where(byte >= 128, byte - 256, byte)
        reconstructed += digit * 256**degree
    padded = torch.zeros((5, words * 4), dtype=torch.int64)
    padded[:, :width] = expected.to(torch.int64)
    assert torch.equal(actual_exponents.cpu(), exponents)
    assert torch.equal(reconstructed.reshape(5, -1), padded)


@gpu
@pytest.mark.parametrize("bits", [14, 22])
def test_narrow_graph_admits_packed_padding_before_workspace_and_matches_cpu(monkeypatch, bits):
    from transformers import LlamaConfig, LlamaForCausalLM

    from heteroes.eval.integer_decoder import IntegerDecoderGraph, IntegerDecoderReference
    import heteroes.eval.strict_decoder_graph as graph_module

    torch.manual_seed(115)
    cpu = (
        LlamaForCausalLM(
            LlamaConfig(
                hidden_size=64,
                intermediate_size=1,
                num_attention_heads=8,
                num_key_value_heads=2,
                num_hidden_layers=1,
                vocab_size=67,
                max_position_embeddings=32,
                eos_token_id=66,
                pad_token_id=0,
            )
        )
        .half()
        .eval()
    )
    backend = IntegerDecoderGraph(copy.deepcopy(cpu).cuda(), magnitude_bits=bits, max_context=32, allow_fixture=True)
    oracle = IntegerDecoderReference(cpu, magnitude_bits=bits, max_context=32, allow_fixture=True)
    weights = tuple(backend._projection_weights())
    metadata_bytes = sum(weight.shape[0] * 4 for weight in {id(w): w for w in weights}.values())
    # Width-one down projection packs into two/three whole words, beyond a single FP32 input slot.
    padding_per_row = (2 if bits == 14 else 3) * 4 - 4
    bound = backend._request_workspace_bytes(3)
    assert bound == metadata_bytes + padding_per_row * 3 * 32
    ids = torch.tensor([[3, 5], [7, 11], [13, 17]], device="cuda")
    with monkeypatch.context() as changes:
        changes.setattr(graph_module, "graph_memory_bound", lambda *args, **kwargs: 0)
        changes.setattr(backend, "max_graph_bytes", bound - 1)
        changes.setattr(backend, "_session_for", lambda *args: pytest.fail("admission must precede graph allocation"))
        changes.setattr(backend, "_generation_begin", lambda: pytest.fail("admission must precede metadata"))
        with pytest.raises(ReferenceArithmeticError, match="budget"):
            backend.generate(ids, max_new_tokens=3, eos_token_id=[])
    expected = oracle.generate(ids.cpu(), max_new_tokens=3, eos_token_id=[])
    assert torch.equal(backend.generate(ids, max_new_tokens=3, eos_token_id=[]).cpu(), expected)
    assert backend._session.capture_count == 1
