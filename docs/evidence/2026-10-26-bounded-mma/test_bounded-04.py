import os

import pytest
import torch

from bounded_reference import block_length, quantize_rows, linear


def test_rational_quantizer_ties_ftz_and_known_dot():
    x = torch.tensor([[1., 1+1/256, 1+3/256, -1-1/256, -1-3/256, -0., 2**-127]])
    q, e = quantize_rows(x, 8)
    assert q.tolist() == [[128, 128, 130, -128, -130, 0, 0]] and e.tolist() == [0]
    y = linear(torch.tensor([[1., -1.]]), torch.tensor([[.5, -.5]], dtype=torch.float16),
               torch.tensor([.25], dtype=torch.float16), activation_bits=8, weight_bits=8)
    assert y.item() == 1.25


def test_block_bound_covers_every_sum_order_and_the_next_integer_is_not_float32():
    for a, w, expected in ((8, 8, 256), (10, 8, 64), (11, 6, 128)):
        length = block_length(a, w)
        assert length == expected
        maximum = length * 2**a * 2**w
        assert maximum == 2**24
        assert torch.tensor(maximum, dtype=torch.float32).double().item() == maximum
        assert torch.tensor(maximum+1, dtype=torch.float32).double().item() != maximum+1
    for a, w in ((True, 8), (12, 8), (11, 11), (5, 8)):
        with pytest.raises(ValueError):
            block_length(a, w)


@pytest.mark.skipif(os.environ.get('HETEROES_GPU_ACCEPTANCE') != '1' or not torch.cuda.is_available(), reason='GPU opt-in')
@pytest.mark.parametrize('a,w', [(8, 8), (10, 8), (11, 6)])
def test_bounded_tensor_core_matches_fraction_oracle_for_tails_offsets_and_split(a, w):
    from bounded_cuda import BoundedKernels
    kernel = BoundedKernels('cuda', activation_bits=a, weight_bits=w)
    generator = torch.Generator().manual_seed(9377)
    for rows, width, outputs, offset in ((1, 65, 7, 0), (8, 128, 9, 1), (19, 67, 13, 0), (3, 257, 7, 0)):
        x = torch.randn(rows, width, generator=generator)
        x[0, :2] = torch.tensor([-0., 2**-127])
        weight = (torch.randn(outputs, width, generator=generator) * .125).half()
        weight[0, 0] = 2.0**-24
        bias = torch.randn(outputs, generator=generator).half()
        backing = torch.empty(weight.numel()+offset, device='cuda', dtype=torch.float16)
        live = backing[offset:].reshape(weight.shape)
        live.copy_(weight)
        expected = linear(x, weight, bias, activation_bits=a, weight_bits=w).view(torch.int32)
        for split in (1, 2, 8):
            actual = kernel.linear(x.cuda(), live, bias.cuda(), split_k=split)
            assert torch.equal(actual.cpu().view(torch.int32), expected), (a, w, rows, width, offset, split)


@pytest.mark.skipif(os.environ.get('HETEROES_GPU_ACCEPTANCE') != '1' or not torch.cuda.is_available(), reason='GPU opt-in')
def test_partial_bound_is_exact_at_equality_and_across_block_boundaries():
    from bounded_cuda import BoundedKernels
    kernel = BoundedKernels('cuda', activation_bits=8, weight_bits=8)
    # 1.999 rounds to coefficient 256; this reaches the exact |partial| <= 2^24 boundary.
    x = torch.full((16, 513), 1.999)
    weight = torch.full((9, 513), 1.999, dtype=torch.float16)
    weight[1, 1::2].neg_()
    expected = linear(x, weight, activation_bits=8, weight_bits=8).view(torch.int32)
    for split in (1, 8):
        actual = kernel.linear(x.cuda(), weight.cuda(), split_k=split, implementation='mma')
        assert torch.equal(actual.cpu().view(torch.int32), expected)


@pytest.mark.skipif(os.environ.get('HETEROES_GPU_ACCEPTANCE') != '1' or not torch.cuda.is_available(), reason='GPU opt-in')
def test_tiny_residual_after_large_cancellation_catches_an_unbounded_float_accumulator():
    from bounded_cuda import BoundedKernels
    kernel = BoundedKernels('cuda', activation_bits=8, weight_bits=8)
    x = torch.full((16, 528), 1.999)
    weight = torch.full((9, 528), 1.999, dtype=torch.float16)
    x[:, 256] = 1/128
    weight[:, 256] = 1/128
    x[:, 257:272] = 0
    weight[:, 272:].neg_()
    expected = linear(x, weight, activation_bits=8, weight_bits=8)
    assert bool((expected == 2.0**-14).all())
    for split in (1, 8):
        actual = kernel.linear(x.cuda(), weight.cuda(), split_k=split, implementation='mma')
        assert torch.equal(actual.cpu().view(torch.int32), expected.view(torch.int32))
