"""Host-side graph constants retain strict FP32 bits without repeated device synchronization."""

import struct

import pytest
import torch

from heteroes.strict import reference_ops as ops
from heteroes.strict.reference_ops import ReferenceArithmeticError
from heteroes.strict.strict_decoder_graph import StrictDecoderGraph


def backend():
    # This helper only constructs a constant; test it on CPU without requiring a CUDA model/context.
    value = object.__new__(StrictDecoderGraph)
    value.device = torch.device("cpu")
    value._inverse_cache = None
    return value


def test_reciprocal_cache_uses_fp32_identity_and_one_bounded_entry(monkeypatch):
    value = backend()
    reciprocal = ops.reciprocal
    penalties = [1.0, 1.0 + 2.0**-25, 1.2, 1.2, 1.0]
    expected = [float(reciprocal(torch.tensor(p, dtype=torch.float32)).item()) for p in penalties]
    calls = []

    def record(tensor):
        calls.append(float(tensor.item()))
        return reciprocal(tensor)

    monkeypatch.setattr(ops, "reciprocal", record)
    actual = [value._inverse_for(p) for p in penalties]
    assert [struct.pack("<f", p) for p in actual] == [struct.pack("<f", p) for p in expected]
    assert len(calls) == 3
    assert value._inverse_cache == (struct.pack("<f", 1.0), expected[-1])


def test_failed_reciprocal_does_not_replace_a_valid_constant(monkeypatch):
    value = backend()
    expected = value._inverse_for(1.2)
    cached = value._inverse_cache
    with pytest.raises(ReferenceArithmeticError):
        value._inverse_for(0.0)
    assert value._inverse_cache == cached
    monkeypatch.setattr(ops, "reciprocal", lambda _: pytest.fail("reuse the last valid constant"))
    assert value._inverse_for(1.2) == expected
