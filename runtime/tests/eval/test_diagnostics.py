"""Pure parts of the cross-GPU diagnostics: the margin between the two best next-token scores at each step of a greedy answer, and
where two answers first differ. (The model parts are exercised by scripts/cross_gpu_sweep.py on the real model.)"""
import pytest
import torch

from heteroes.eval.diagnostics import first_divergence, margins_from_scores, summarize_pair


def test_margin_is_top1_minus_top2_of_each_step_by_hand():
    # step 0: scores [1.0, 3.5, 3.0] -> top1 3.5, top2 3.0 -> margin 0.5 ; step 1: [0.0, -1.0, 4.0] -> 4.0 - 0.0 = 4.0
    scores = (torch.tensor([[1.0, 3.5, 3.0]]), torch.tensor([[0.0, -1.0, 4.0]]))
    assert margins_from_scores(scores, row=0) == pytest.approx([0.5, 4.0])


def test_margin_uses_the_requested_row_of_a_batch():
    scores = (torch.tensor([[1.0, 2.0], [5.0, 0.0]]),)
    assert margins_from_scores(scores, row=0) == pytest.approx([1.0])
    assert margins_from_scores(scores, row=1) == pytest.approx([5.0])


def test_a_tie_has_margin_zero_and_infinities_of_the_processors_do_not_break_it():
    scores = (torch.tensor([[2.0, 2.0, -float("inf")]]),)
    assert margins_from_scores(scores, row=0) == [0.0]
    only_one_allowed = (torch.tensor([[2.0, -float("inf"), -float("inf")]]),)
    assert margins_from_scores(only_one_allowed, row=0) == [float("inf")]


def test_margins_are_float64_numbers_of_the_scores_as_given():
    scores = (torch.tensor([[1.0, 0.5]], dtype=torch.float16),)
    value = margins_from_scores(scores, row=0)[0]
    assert isinstance(value, float) and value == 0.5


def test_first_divergence_by_hand():
    assert first_divergence([1, 2, 3, 4], [1, 2, 9, 4]) == 2
    assert first_divergence([1, 2, 3], [1, 2, 3]) is None
    assert first_divergence([1, 2, 3], [1, 2, 3, 4]) == 3          # one is a prefix of the other: they differ where the shorter ends
    assert first_divergence([], [7]) == 0
    assert first_divergence([], []) is None


def test_summarize_pair_reports_the_step_and_the_margins_there():
    a = {"ids": [5, 6, 7, 8], "margins": [9.0, 8.0, 0.25, 7.0]}
    b = {"ids": [5, 6, 9, 8], "margins": [9.0, 8.0, 0.5, 7.0]}
    assert summarize_pair(a, b) == {"differs": True, "step": 2, "margin_a": 0.25, "margin_b": 0.5, "min_margin_before": 8.0}


def test_summarize_pair_of_equal_answers_says_so():
    a = {"ids": [5, 6], "margins": [1.0, 2.0]}
    assert summarize_pair(a, dict(a)) == {"differs": False}


def test_summarize_pair_when_one_answer_ends_early_has_no_margin_after_the_end():
    a = {"ids": [5, 6], "margins": [1.0, 2.0]}
    b = {"ids": [5, 6, 7], "margins": [1.0, 2.0, 3.0]}
    result = summarize_pair(a, b)
    assert result["differs"] and result["step"] == 2 and result["margin_a"] is None and result["margin_b"] == 3.0
