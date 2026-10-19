"""
Coordinator-side scoring (ADR-008 section 7). The built-in scorers must give today's rewards on real recorded texts; a
scorer failure must raise, never become a reward of 0.
"""

import json
import math
from pathlib import Path

import pytest

import heteroes.eval.cot_workload as cot
from heteroes.v3.scoring import DECLARATIVE, ScorerError, code_sha256, score, validate_spec

ARTIFACTS = Path(__file__).resolve().parents[2] / "artifacts"


def spec(name, config=None, kind="declarative", code=None, version=1):
    return {"kind": kind, "name": name, "version": version, "codeSha256": code, "config": config or {}}


def recorded_arith16_evaluations():
    """Every (records, mean_reward) the arith16 probes and regressions wrote, with the reward of each record."""
    found = []

    def walk(value):
        if isinstance(value, dict):
            if isinstance(value.get("records"), list) and value["records"] and "output_text" in value["records"][0]:
                found.append((value["records"], value["mean_reward"]))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    for path in sorted(ARTIFACTS.rglob("*.json")):
        text = path.read_text(encoding="utf-8")
        if '"output_text"' in text:
            walk(json.loads(text))
    return found


def test_last_integer_gives_the_recorded_arith16_rewards():
    evaluations = recorded_arith16_evaluations()
    assert len(evaluations) >= 20 and any(mean not in (0.0, 1.0) for _, mean in evaluations)  # premise: varied data
    for records, mean in evaluations:
        texts = [r["output_text"] for r in records]
        rows = [{"answer": r["expected"]} for r in records]
        reward, scores = score(spec("last-integer"), texts, rows)
        assert scores == [r["reward"] for r in records]
        assert reward == mean


def test_answer_line_integer_gives_what_todays_cot_evaluation_gives_on_recorded_texts(monkeypatch):
    recorded = json.loads((ARTIFACTS / "experiments/2026-10-09-chunk128/texts-5070ti.json").read_text())
    assert recorded["workload"] == "cot_l1_q128"
    rows = [{"answer": answer} for _, answer in cot.make_questions(128, 1)]
    rewards = set()
    for condition in recorded["conditions"]:
        texts = condition["texts"]
        monkeypatch.setattr(cot, "generate", lambda *args, texts=texts, **kwargs: (texts, 0))
        today = cot.evaluate_cot(None, None, 64, level=1, count=128)
        reward, scores = score(spec("answer-line-integer"), texts, rows)
        assert scores == [r.reward for r in today.records] and reward == today.mean_reward
        rewards.add(reward)
    assert len(rewards) > 1  # premise: the conditions differ, so a constant scorer would fail


def test_answer_line_last_number_normalizes_like_recipe_v2():
    texts = ["so 1,003 pens. Answer: 1,003", "Answer: $5.50", "no number here", "Answer: 7\nAnswer: 8"]
    rows = [{"answer": "1003"}, {"answer": "5.5"}, {"answer": "0"}, {"answer": "7"}]
    assert score(spec("answer-line-last-number"), texts, rows) == (0.5, [1.0, 1.0, 0.0, 0.0])


def test_the_configurable_scorers():
    rows = [{"label": "Paris"}, {"label": " B "}]
    assert score(
        spec("exact-string", {"answerField": "label", "strip": True, "casefold": True}), [" paris\n", "b"], rows
    )[1] == [1.0, 1.0]
    assert score(
        spec("exact-string", {"answerField": "label", "strip": False, "casefold": False}), ["Paris", "B"], rows
    )[1] == [1.0, 0.0]
    regex = spec("regex", {"pattern": r"capital: (\w+)", "answerField": "label"})
    assert score(regex, ["capital: Rome then capital: Paris", "none"], rows)[1] == [1.0, 0.0]
    choice = spec("choice-letter", {"answerField": "label"})
    assert score(choice, ["A or maybe C", "I pick B."], [{"label": "c"}, {"label": "B"}])[1] == [1.0, 1.0]
    assert score(choice, ["ABC", "Answer: D"], [{"label": "A"}, {"label": "B"}])[1] == [0.0, 0.0]


@pytest.mark.parametrize(
    "scorer",
    [
        lambda c, r: 1 / 0,
        lambda c, r: [math.nan] * len(r),
        lambda c, r: [math.inf] * len(r),
        lambda c, r: [True] * len(r),
        lambda c, r: [1.0],
        lambda c, r: None,
        lambda c, r: ["1"] * len(r),
    ],
)
def test_a_failing_python_scorer_raises_instead_of_giving_zero(scorer):
    with pytest.raises(ScorerError):
        score(spec("mine", kind="python", code="a" * 64), ["x", "y"], [{}, {}], python_scorer=scorer)


def test_python_scorer_reward_is_the_row_mean_and_it_cannot_change_the_rows():
    def scorer(completions, rows):
        rows[0]["answer"] = "changed"
        return [len(text) for text in completions]

    rows = [{"answer": "1"}, {"answer": "2"}]
    assert score(spec("mine", kind="python", code="a" * 64), ["ab", "abcd"], rows, python_scorer=scorer) == (
        3.0,
        [2.0, 4.0],
    )
    assert rows[0]["answer"] == "1"
    with pytest.raises(ScorerError, match="not loaded"):
        score(spec("mine", kind="python", code="a" * 64), ["ab"], [{}])


def test_mismatched_texts_and_rows_are_refused():
    with pytest.raises(ScorerError):
        score(spec("last-integer"), ["1"], [{"answer": 1}, {"answer": 2}])
    with pytest.raises(ScorerError):
        score(spec("last-integer"), [], [])
    with pytest.raises(ScorerError):
        score(spec("last-integer"), [None], [{"answer": 1}])


def test_specs_are_strict_and_a_shared_lab_refuses_python():
    for name, versions in DECLARATIVE.items():
        for version, (_, keys) in versions.items():
            config = {k: ("x" if k == "pattern" or k.endswith("Field") else False) for k in keys}
            assert validate_spec(spec(name, config, version=version))
    python = spec("mine", kind="python", code="a" * 64)
    with pytest.raises(ValueError, match="only declarative"):
        validate_spec(python)
    assert validate_spec(python, allow_python=True)
    bad = [
        spec("last-integer", version=2),
        spec("unknown"),
        spec("last-integer", {"extra": 1}),
        spec("last-integer", code="a" * 64),
        spec("regex", {"pattern": "(", "answerField": "a"}),
        spec("regex", {"pattern": "", "answerField": "a"}),
        spec("exact-string", {"answerField": "a", "strip": 1, "casefold": False}),
        spec("choice-letter", {"answerField": ""}),
        spec("countdown", {"numbersField": "nums", "targetField": ""}),
        spec("countdown", {"numbersField": 1, "targetField": "target"}),
        spec("countdown", {"numbersField": "nums"}),
        spec("Bad Name"),
        spec("mine", kind="python", code="short"),
        spec("mine", kind="other"),
        {**spec("last-integer"), "extra": 1},
    ]
    for value in bad:
        with pytest.raises(ValueError):
            validate_spec(value, allow_python=True)


def test_code_identity_covers_names_and_contents(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg/a.py").write_text("x = 1\n")
    (tmp_path / "pkg/b.py").write_text("y = 2\n")
    first = code_sha256(tmp_path / "pkg")
    assert code_sha256(tmp_path / "pkg") == first
    (tmp_path / "pkg/b.py").write_text("y = 3\n")
    assert code_sha256(tmp_path / "pkg") != first
    (tmp_path / "pkg/b.py").write_text("y = 2\n")
    (tmp_path / "pkg/b.py").rename(tmp_path / "pkg/c.py")
    assert code_sha256(tmp_path / "pkg") != first
    assert code_sha256(tmp_path / "pkg/a.py") != code_sha256(tmp_path / "pkg/c.py")


def test_regex_with_several_groups_compares_the_first_and_case_is_kept_without_casefold():
    regex = spec("regex", {"pattern": r"(\w+) is the (answer)", "answerField": "label"})
    assert score(regex, ["Lyon is the answer, no: Paris is the answer"], [{"label": "Paris"}])[1] == [1.0]
    exact = spec("exact-string", {"answerField": "label", "strip": True, "casefold": False})
    assert score(exact, ["paris", "Paris "], [{"label": "Paris"}, {"label": "Paris"}])[1] == [0.0, 1.0]


@pytest.mark.parametrize("error", [KeyError("answer"), RuntimeError("boom"), TypeError("bad")])
def test_any_exception_of_a_scorer_becomes_a_scorer_error(error):
    def scorer(completions, rows):
        raise error

    with pytest.raises(ScorerError):
        score(spec("mine", kind="python", code="a" * 64), ["x"], [{}], python_scorer=scorer)
    with pytest.raises(ScorerError, match="KeyError"):
        score(spec("regex", {"pattern": "x", "answerField": "missing"}), ["x"], [{}])  # a declarative scorer too


COUNTDOWN = spec("countdown", {"numbersField": "nums", "targetField": "target"})


def countdown(texts, nums="3 7 25 50", target=94):
    rows = [{"nums": nums, "target": target}] * len(texts)
    return score(COUNTDOWN, texts, rows)[1]


def test_countdown_gives_one_for_a_correct_equation_that_uses_every_number_once():
    # TinyZero/ES-at-Scale reward: 1.0 correct, 0.1 an answer that is well formed but wrong, 0.0 no answer
    assert countdown(["<think>50+25=75</think> <answer>(50 + 25) + 7*3 - 2</answer>"]) == [0.1]  # 2 is not given
    assert countdown(["<answer>50 + 25 + 7 * 3 - 2</answer>"], nums="2 3 7 25 50") == [1.0]
    assert countdown(["<answer> 50 + 25 + 3*7 </answer>"], target=96) == [1.0]
    assert countdown(["<answer>(50 + 25 + 3*7)</answer>"], nums="[50, 25, 3, 7]", target=96) == [1.0]
    # division is exact (fractions), not floating point
    assert countdown(["<answer>(7 - 3) / (50 / 25)</answer>"], target=2) == [1.0]
    assert countdown(["<answer>7 / 3 * 3 + 50 - 25</answer>"], nums="3 3 7 25 50", target=32) == [1.0]
    assert countdown(["<answer>(1 / 10 + 2 / 10) * 10</answer>"], nums="1 2 10 10 10", target=3) == [1.0]
    # the last answer counts; an earlier correct one does not
    assert countdown(["<answer>50+25+3*7</answer> wait <answer>50+25+3+7</answer>"], target=96) == [0.1]


def test_countdown_gives_format_credit_only_when_numbers_or_value_are_wrong():
    assert countdown(["<answer>50 + 25 + 7</answer>"], target=82) == [0.1]  # 3 unused
    assert countdown(["<answer>50 + 50 + 3 - 7</answer>"], target=96) == [0.1]  # 50 twice, 25 unused
    assert countdown(["<answer>50 + 25 + 3 + 7</answer>"]) == [0.1]  # 85, not 94
    assert countdown(["<answer>50 / (25 - 25) + 3 + 7</answer>"]) == [0.1]  # division by zero
    assert countdown(["<answer>2 ** 3 + 1</answer>"], nums="1 2 3", target=9) == [0.1]  # power is not an operation
    assert countdown(["<answer>-50 + 25 + 3 * 7</answer>"], target=-4) == [0.1]  # unary minus is not allowed
    assert countdown(["<answer>50 + 25 + 3.5 + 7</answer>"]) == [0.1]
    assert countdown(["<answer>50 + 25 + 3 * 7.0</answer>"], target=96) == [0.1]  # numbers are integers
    assert countdown(["<answer>__import__('os')</answer>"]) == [0.1]
    assert countdown(["<answer>(50 + 25</answer>"]) == [0.1]
    assert countdown(["<answer></answer>"]) == [0.1]


def test_countdown_gives_zero_without_an_answer():
    assert countdown(["50 + 25 + 3 * 7 = 96"], target=96) == [0.0]
    assert countdown(["<answer>50 + 25 + 3 * 7"], target=96) == [0.0]
    assert countdown([""]) == [0.0]


def test_countdown_reads_its_columns_and_a_bad_row_is_a_scorer_fault():
    rows = [{"n": "1 2", "t": 3}]
    other = spec("countdown", {"numbersField": "n", "targetField": "t"})
    assert score(other, ["<answer>1+2</answer>"], rows)[1] == [1.0]
    with pytest.raises(ScorerError):
        score(other, ["<answer>1+2</answer>"], [{"n": "1 two", "t": 3}])
    with pytest.raises(ScorerError):
        score(other, ["<answer>1+2</answer>"], [{"n": "1 2"}])
