import pytest
import torch
import torch.nn as nn

from heteroes.model.schema import SchemaMismatchError, build_parameter_schema, resolve_tensors


class Toy(nn.Module):
    # Like Qwen in miniature: a tied tensor first, plain tensors afterwards.
    # Parameters (canonical order): embed.weight (tied with head.weight), fc.weight, fc.bias.
    def __init__(self, tied=True, fc_out=4, fc_name="fc", with_fc=True, fc_first=False, extra=False):
        super().__init__()

        def add_fc():
            if with_fc:
                setattr(self, fc_name, nn.Linear(4, fc_out))

        if fc_first:
            add_fc()
        self.embed = nn.Embedding(10, 4)
        self.head = nn.Linear(4, 10, bias=False)
        if tied:
            self.head.weight = self.embed.weight
        if not fc_first:
            add_fc()
        if extra:
            self.extra = nn.Parameter(torch.zeros(2))


def test_returns_the_live_tensors_in_schema_order():
    model = Toy()
    schema = build_parameter_schema(model)

    tensors = resolve_tensors(model, schema)

    expected = [p for _, p in model.named_parameters()]
    assert len(tensors) == len(expected) == len(schema.entries)
    for got, want in zip(tensors, expected):
        assert got.data_ptr() == want.data_ptr()  # live memory, not a copy
        assert got.shape == want.shape


def test_a_tied_tensor_appears_once():
    model = Toy(tied=True)
    schema = build_parameter_schema(model)

    tensors = resolve_tensors(model, schema)

    assert len(tensors) == 3
    assert sum(t.data_ptr() == model.embed.weight.data_ptr() for t in tensors) == 1


def test_a_second_model_with_the_same_layout_matches():
    schema = build_parameter_schema(Toy())

    assert len(resolve_tensors(Toy(), schema)) == 3


@pytest.mark.parametrize(
    "other",
    [
        pytest.param(dict(fc_name="proj"), id="renamed"),
        pytest.param(dict(fc_out=5), id="shape changed"),
        pytest.param(dict(extra=True), id="extra parameter"),
        pytest.param(dict(with_fc=False), id="missing parameters"),
        pytest.param(dict(fc_first=True), id="different order"),
        pytest.param(dict(tied=False), id="weight tying removed"),
    ],
)
def test_a_model_that_differs_from_the_schema_is_rejected(other):
    schema = build_parameter_schema(Toy())

    with pytest.raises(SchemaMismatchError):
        resolve_tensors(Toy(**other), schema)


def test_a_different_dtype_is_rejected():
    schema = build_parameter_schema(Toy())  # float32

    with pytest.raises(SchemaMismatchError):
        resolve_tensors(Toy().half(), schema)


def test_resolving_does_not_change_the_model():
    model = Toy()
    before = [p.detach().clone() for p in model.parameters()]

    resolve_tensors(model, build_parameter_schema(model))

    assert all(torch.equal(a, b) for a, b in zip(before, model.parameters()))
