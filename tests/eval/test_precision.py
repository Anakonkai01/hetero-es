"""`EvalModel`: the model the evaluation runs on. FP16: the live model itself. FP32: a float32 shadow copy that is refreshed from the live FP16
weights (an exact widening) before each evaluation; the live weights, the noise and the update never change precision."""
import pytest
import torch
import torch.nn as nn

from heteroes.eval.precision import EvalModel


class HalfToy(nn.Module):
    def __init__(self, seed=0):
        super().__init__()
        torch.manual_seed(seed)
        self.embed = nn.Embedding(10, 4)
        self.head = nn.Linear(4, 10, bias=False)
        self.head.weight = self.embed.weight                 # tied, like Qwen
        self.fc = nn.Linear(4, 4)
        self.half()


def bits(model):
    return [p.detach().clone().view(torch.int16) for p in model.parameters()]


def test_in_float16_the_evaluation_runs_on_the_live_model_itself_and_refresh_does_nothing():
    live = HalfToy()
    evaluation = EvalModel(live, "float16")
    assert evaluation.model is live
    before = bits(live)
    evaluation.refresh()
    assert all(torch.equal(a, b) for a, b in zip(before, bits(live)))


def test_in_float32_the_evaluation_runs_on_a_float32_copy_with_the_tie_kept():
    live = HalfToy()
    evaluation = EvalModel(live, "float32")
    shadow = evaluation.model
    assert shadow is not live
    assert all(p.dtype == torch.float32 for p in shadow.parameters()) and all(p.dtype == torch.float16 for p in live.parameters())
    assert shadow.embed.weight is shadow.head.weight                   # one tensor, as in the live model: a perturbation of it is seen by both uses
    assert len(list(shadow.parameters())) == len(list(live.parameters()))


def test_the_shadow_starts_as_the_exact_widening_of_the_live_weights():
    live = HalfToy()
    shadow = EvalModel(live, "float32").model
    for a, b in zip(live.parameters(), shadow.parameters()):
        assert torch.equal(a.float(), b)


def test_refresh_makes_the_shadow_follow_the_live_weights_exactly_and_never_touches_the_live_ones():
    live = HalfToy()
    evaluation = EvalModel(live, "float32")
    with torch.no_grad():                                              # the live weights change (a perturbation)
        for parameter in live.parameters():
            parameter.add_(torch.full_like(parameter, 0.25))
    stale = [p.clone() for p in evaluation.model.parameters()]
    assert not all(torch.equal(a.float(), b) for a, b in zip(live.parameters(), stale))      # premise: now they differ
    live_bits = bits(live)

    evaluation.refresh()

    for a, b in zip(live.parameters(), evaluation.model.parameters()):
        assert torch.equal(a.float(), b)
    assert all(torch.equal(x, y) for x, y in zip(live_bits, bits(live)))


def test_the_shadow_is_not_a_view_of_the_live_weights():
    live = HalfToy()
    evaluation = EvalModel(live, "float32")
    with torch.no_grad():
        evaluation.model.fc.bias.add_(1.0)                              # a change of the shadow...
    assert not torch.equal(live.fc.bias.float(), evaluation.model.fc.bias)       # ... is not a change of the live model


@pytest.mark.parametrize("bad", ["bfloat16", "float64", "", None])
def test_an_unknown_precision_is_refused(bad):
    with pytest.raises(ValueError):
        EvalModel(HalfToy(), bad)


@pytest.mark.skipif(not torch.cuda.is_available(), reason="no GPU")
def test_on_the_gpu_the_shadow_lives_on_the_same_device_and_follows_the_live_weights():
    live = HalfToy().cuda()
    evaluation = EvalModel(live, "float32")
    assert next(evaluation.model.parameters()).device == next(live.parameters()).device
    with torch.no_grad():
        for parameter in live.parameters():
            parameter.mul_(2)
    evaluation.refresh()
    for a, b in zip(live.parameters(), evaluation.model.parameters()):
        assert torch.equal(a.float(), b)
