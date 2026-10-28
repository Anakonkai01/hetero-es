import torch

from margin_guard import MarginGuard


def test_only_ambiguous_row_is_recomputed_with_its_exact_prefix():
    calls = []

    def reference(row, prefix):
        calls.append((row, prefix.tolist()))
        return torch.tensor([0.0, 3.0, 1.0])

    guard = MarginGuard(0.01, reference)
    ids = torch.tensor([[1, 2], [3, 4]])
    scores = torch.tensor([[5.0, 1.0, 0.0], [2.0, 1.999, 0.0]])
    original = scores.clone()
    result = guard(ids, scores)
    assert calls == [(1, [[3, 4]])]
    assert torch.equal(result[0], original[0])
    assert result.argmax(-1).tolist() == [0, 1]
    assert torch.equal(scores, original)


def test_multiple_ambiguous_rows_and_no_ambiguity():
    calls = []

    def reference(row, prefix):
        calls.append(row)
        return torch.tensor([1.0, 0.0, 2.0])

    guard = MarginGuard(0.01, reference)
    ids = torch.tensor([[1], [2]])
    scores = torch.tensor([[1.0, 1.0, 0.0], [0.0, 1.0, 1.0]])
    result = guard(ids, scores)
    assert calls == [0, 1]
    assert result.argmax(-1).tolist() == [2, 2]
    calls.clear()
    stable = torch.tensor([[9.0, 0.0, 0.0], [0.0, 0.0, 9.0]])
    assert torch.equal(guard(ids, stable), stable)
    assert calls == []
