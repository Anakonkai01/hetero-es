"""Helpers of the second learning experiment (`artifacts/experiments/2026-10-08-learning-v2/learnlib2.py`): the sets, the token-limit switch, the checkpoint choice, the verdict."""
import importlib.util
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PATH = Path(os.environ.get("LEARNLIB2_PATH") or ROOT / "artifacts/experiments/2026-10-08-learning-v2/learnlib2.py")      # LEARNLIB2_PATH: a mutant, for the mutation check
spec = importlib.util.spec_from_file_location("learnlib2", PATH)
l2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(l2)


def test_the_training_set_is_the_128_questions_of_the_workload():
    from heteroes.eval.cot_workload import make_questions
    assert l2.train_questions() == make_questions(128, 1)


def test_the_sets_have_their_sizes_and_none_shares_a_question_with_the_training_set():
    train = {q for q, _ in l2.train_questions()}
    sets = l2.heldout_sets()

    assert set(sets) == {"H1", "V1", "H2", "H3"}
    assert [len(sets[k]) for k in ("H1", "V1", "H2", "H3")] == [256, 256, 128, 128]
    for name, qa in sets.items():
        assert not ({q for q, _ in qa} & train), name


def test_the_validation_set_and_the_test_set_of_the_training_family_are_different_questions():
    sets = l2.heldout_sets()

    assert not ({q for q, _ in sets["H1"]} & {q for q, _ in sets["V1"]})


def test_a_collision_with_the_training_set_is_replaced_and_the_size_kept(monkeypatch):
    from heteroes.eval.cot_workload import make_questions
    first = make_questions(256 + 128, 1, l2.SEEDS["H1"])[0][0]
    monkeypatch.setattr(l2, "train_questions", lambda: [(first, 0)])

    h1 = l2.heldout_sets()["H1"]

    assert len(h1) == 256 and first not in {q for q, _ in h1}


def test_the_token_limit_is_switched_for_the_block_and_restored_after_an_error():
    import heteroes.eval.cot_workload as cot
    before = cot.MAX_NEW_TOKENS
    with l2.token_limit(512):
        assert cot.MAX_NEW_TOKENS == 512
    assert cot.MAX_NEW_TOKENS == before
    with pytest.raises(RuntimeError):
        with l2.token_limit(777):
            raise RuntimeError("x")
    assert cot.MAX_NEW_TOKENS == before


def test_select_checkpoint_takes_the_best_validation_score_and_the_earliest_on_a_tie_and_ignores_the_base():
    assert l2.select_checkpoint({0: 0.99, 5: 0.60, 10: 0.70, 15: 0.70, 20: 0.65}) == 10
    assert l2.select_checkpoint({0: 0.1, 5: 0.2}) == 5


def test_select_checkpoint_needs_a_checkpoint_after_the_base():
    with pytest.raises(ValueError):
        l2.select_checkpoint({0: 0.5})


def s(acc):
    return {"accuracy": acc}


BASE = {"train": s(0.50), "H1": s(0.65), "H2": s(0.94), "H3": s(0.80)}


def good(**over):
    sel = {"train": s(0.62), "H1": s(0.72), "H2": s(0.94), "H3": s(0.80)}
    sel.update({k: s(v) for k, v in over.items()})
    return sel


def stable(h2=0.94, h3=0.80):
    return {"H2": h2, "H3": h3}


def test_all_four_criteria_met():
    v = l2.verdict(BASE, good(), non_tie_pos=30, non_tie_neg=10, last3_mean=stable(), walks_lower=[True, True, True])

    assert (v["P1"], v["P2"], v["P3"], v["P4"]) == (True, True, True, True) and v["label"].startswith("ES improved held-out accuracy")


@pytest.mark.parametrize("sel_h1,expected", [(0.65 + 0.06, True), (0.65 + 0.0599, False)])
def test_p1_threshold_is_six_points_inclusive(sel_h1, expected):
    assert l2.verdict(BASE, good(H1=sel_h1), 30, 10, stable(), [True] * 3)["P1"] is expected


@pytest.mark.parametrize("pos,neg,expected", [(30, 10, True), (12, 8, True), (11, 9, False), (9, 9, False), (60, 41, True), (15, 3, False)])
def test_p2_needs_sixty_percent_of_the_non_ties_a_sign_test_and_at_least_twenty_non_ties(pos, neg, expected):
    # (12, 8): 60 percent but p = 0.25 -> must be False; the cases are written with the real rule below
    result = l2.verdict(BASE, good(), pos, neg, stable(), [True] * 3)["P2"]
    rule = (pos + neg >= 20) and pos / (pos + neg) >= 0.6 and l2.sign_test_p(pos, neg) <= 0.05
    assert result is rule


def test_p2_needs_every_shuffled_walk_to_end_below_the_real_trajectory():
    assert l2.verdict(BASE, good(), 30, 10, stable(), [True, True, False])["P2"] is False
    assert l2.verdict(BASE, good(), 30, 10, stable(), [])["P2"] is False


@pytest.mark.parametrize("train,expected", [(0.58, True), (0.5799, False)])
def test_p3_threshold_is_eight_points_inclusive(train, expected):
    assert l2.verdict(BASE, good(train=train), 30, 10, stable(), [True] * 3)["P3"] is expected


@pytest.mark.parametrize("h2,h3,expected", [(0.88, 0.80, True), (0.8799, 0.80, False), (0.94, 0.74, True), (0.94, 0.7399, False)])
def test_p4_is_the_mean_of_the_last_three_checkpoints_and_allows_six_points(h2, h3, expected):
    assert l2.verdict(BASE, good(), 30, 10, stable(h2, h3), [True] * 3)["P4"] is expected


def test_labels_for_the_other_outcomes():
    improved_not_directed = l2.verdict(BASE, good(), 12, 11, stable(), [True] * 3)
    assert improved_not_directed["label"].startswith("held-out accuracy improved but the direction")
    none = l2.verdict(BASE, good(H1=0.65), 30, 10, stable(), [True] * 3)
    assert none["label"] == "no evidence of improvement on held-out arithmetic in this experiment"
