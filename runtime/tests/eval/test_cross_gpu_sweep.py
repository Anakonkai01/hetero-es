"""`scripts/cross_gpu_sweep.py: compare_sweeps`: joining two sweeps by seed and finding the prompts whose answers differ (pure function)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import cross_gpu_sweep as sweep  # noqa: E402


def prompt(ids, margins):
    return {"text": "".join(map(str, ids)), "ids": ids, "margins": margins}


def candidate(seed, reward, prompts):
    return {"kind": "candidate", "seed": seed, "reward": reward, "prompts": prompts}


SAME = [prompt([1, 2], [5.0, 6.0])] * 16


def test_identical_sweeps_have_no_difference():
    a = {s: candidate(s, 0.25, SAME) for s in range(3)}
    result = sweep.compare_sweeps(a, dict(a))
    assert result["candidates_compared"] == 3 and result["prompts_compared"] == 48
    assert result["candidates_with_a_different_answer"] == 0 and result["prompts_with_a_different_answer"] == 0
    assert result["differences"] == [] and result["rate_candidates_with_difference"] == 0.0


def test_one_flipped_prompt_is_found_with_its_step_and_margins():
    # candidate 1, prompt 3: the answers diverge at step 1; the margins there are 0.25 on A and 0.5 on B
    flipped_a = list(SAME)
    flipped_b = list(SAME)
    flipped_a[3] = prompt([1, 2], [5.0, 0.25])
    flipped_b[3] = prompt([1, 9], [5.0, 0.5])
    a = {0: candidate(0, 0.25, SAME), 1: candidate(1, 0.25, flipped_a)}
    b = {0: candidate(0, 0.25, SAME), 1: candidate(1, 0.1875, flipped_b)}

    result = sweep.compare_sweeps(a, b)

    assert result["candidates_with_a_different_answer"] == 1 and result["candidates_with_a_different_reward"] == 1
    assert result["prompts_with_a_different_answer"] == 1
    assert result["rate_candidates_with_difference"] == 0.5 and result["rate_prompts_with_difference"] == pytest.approx(1 / 32)
    (entry,) = result["differences"]
    assert (entry["seed"], entry["prompt"], entry["step"]) == (1, 3, 1)
    assert (entry["margin_a"], entry["margin_b"]) == (0.25, 0.5) and entry["min_margin_before"] == 5.0
    assert result["margin_at_flip"] == {"median": 0.25, "max": 0.25}


def test_only_the_seeds_present_in_both_files_are_compared():
    a = {s: candidate(s, 0.25, SAME) for s in range(5)}
    b = {s: candidate(s, 0.25, SAME) for s in range(3, 8)}
    assert sweep.compare_sweeps(a, b)["candidates_compared"] == 2


def test_two_different_prompts_of_one_candidate_count_one_candidate_and_two_prompts():
    pa = list(SAME)
    pb = list(SAME)
    for index in (2, 9):
        pa[index], pb[index] = prompt([1], [1.0]), prompt([2], [1.0])
    result = sweep.compare_sweeps({0: candidate(0, 0.5, pa)}, {0: candidate(0, 0.5, pb)})
    assert result["candidates_with_a_different_answer"] == 1 and result["prompts_with_a_different_answer"] == 2


def test_seeds_argument():
    assert sweep.parse_seeds("3:6") == [3, 4, 5]
    with pytest.raises(SystemExit):
        sweep.parse_seeds("6:3")
    with pytest.raises(SystemExit):
        sweep.parse_seeds("x:3")
