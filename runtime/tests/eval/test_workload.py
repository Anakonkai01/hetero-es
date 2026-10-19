import dataclasses
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from heteroes.eval.workload import (
    DO_SAMPLE,
    EXAMPLES,
    MAX_NEW_TOKENS,
    REWARD_TYPE,
    SYSTEM_PROMPT,
    Example,
    canonical_json_hash,
    exact_match_reward,
    extract_integer,
    workload_dict,
    workload_hash,
)

# Hash of the workload recorded by the physical probes on both machines (2026-09-29).
PROBE_WORKLOAD_HASH = "cad822bc1e65a9ec37d948e5415cff22c70f96500e2043e6299bbdd5cea0b8d5"

PROBE_JSON = (
    Path(__file__).resolve().parents[2] / "artifacts" / "probes" / "2026-09-29" / "probe_5070ti.json"
)


# ---------------------------------------------------------------------------
# the workload is the one the probe recorded
# ---------------------------------------------------------------------------

def test_workload_hash_is_the_one_recorded_by_the_probes():
    assert workload_hash() == PROBE_WORKLOAD_HASH


def test_workload_hash_is_the_canonical_hash_of_workload_dict():
    assert workload_hash() == canonical_json_hash(workload_dict())


def test_workload_dict_has_exactly_the_probe_fields():
    data = workload_dict()

    assert set(data) == {"system_prompt", "max_new_tokens", "do_sample", "reward_type", "examples"}
    assert data["system_prompt"] == "You are a calculator. Answer with only with number"
    assert data["max_new_tokens"] == 16
    assert data["do_sample"] is False
    assert data["reward_type"] == "exact_integer_match"
    assert all(set(e) == {"question", "answer"} for e in data["examples"])


@pytest.mark.parametrize(
    "path, value",
    [
        (("system_prompt",), "You are a calculator."),
        (("max_new_tokens",), 17),
        (("do_sample",), True),
        (("reward_type",), "something_else"),
        (("examples", 0, "answer"), 42),
        (("examples", 15, "question"), "What is 1 + 1?"),
    ],
)
def test_any_change_of_the_workload_changes_the_hash(path, value):
    # The hash must be able to tell a different workload from this one.
    data = json.loads(json.dumps(workload_dict()))  # deep copy
    target = data
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value

    assert canonical_json_hash(data) != workload_hash()


def test_dropping_or_reordering_an_example_changes_the_hash():
    data = json.loads(json.dumps(workload_dict()))
    reordered = dict(data, examples=list(reversed(data["examples"])))
    shorter = dict(data, examples=data["examples"][:-1])

    assert canonical_json_hash(reordered) != workload_hash()
    assert canonical_json_hash(shorter) != workload_hash()


# ---------------------------------------------------------------------------
# the data itself: independent oracle for the answers
# ---------------------------------------------------------------------------

def test_there_are_16_examples_with_integer_answers_and_distinct_questions():
    assert len(EXAMPLES) == 16
    assert all(isinstance(e.answer, int) and not isinstance(e.answer, bool) for e in EXAMPLES)
    assert len({e.question for e in EXAMPLES}) == 16


def test_the_twelve_arithmetic_answers_are_right():
    # The expression is computed by Python itself, not copied from the table. "What is (144 / 12) * 37?"
    # divides, so compare as numbers: 444.0 == 444.
    for example in EXAMPLES[:12]:
        expression = re.fullmatch(r"What is (.+)\?", example.question).group(1)
        assert re.fullmatch(r"[0-9+\-*/() ]+", expression)  # only arithmetic reaches eval
        assert eval(expression, {"__builtins__": {}}) == example.answer, example.question


def test_the_four_word_problem_answers_are_right():
    # Worked by hand from the text of each problem.
    expected = {
        12: 48 * 36 - 725,    # pens remaining
        13: 36 * 24 - 579,    # notebooks remaining
        14: 72 * 5 + 148,     # total distance
        15: 125 * 18 - 347,   # usable items
    }
    assert [EXAMPLES[i].answer for i in expected] == list(expected.values()) == [1003, 285, 508, 1903]


def test_the_workload_cannot_be_changed_by_accident():
    assert isinstance(EXAMPLES, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        EXAMPLES[0].answer = 0
    assert (SYSTEM_PROMPT, MAX_NEW_TOKENS, DO_SAMPLE, REWARD_TYPE) == (
        "You are a calculator. Answer with only with number", 16, False, "exact_integer_match",
    )


# ---------------------------------------------------------------------------
# extract_integer
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "text, expected",
    [
        ("41", 41),
        (" 6292\n", 6292),
        ("The answer is 1,003.", 1003),
        ("1,234,567", 1234567),
        ("3 and then 7", 7),        # the LAST integer wins
        ("-5", -5),
        ("12 apples", 12),
        ("no number here", None),
        ("", None),
    ],
)
def test_extract_integer(text, expected):
    assert extract_integer(text) == expected


@pytest.mark.parametrize("text, expected", [("5-3", -3), ("3.5", 5)])
def test_extract_integer_keeps_the_quirks_of_the_probe(text, expected):
    # Deliberate compatibility with the probe (see the docstring): "5-3" -> -3 and "3.5" -> 5.
    assert extract_integer(text) == expected


# ---------------------------------------------------------------------------
# exact_match_reward
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "prediction, expected, reward",
    [(41, 41, 1.0), (40, 41, 0.0), (None, 41, 0.0), (None, 0, 0.0), (-41, 41, 0.0), (0, 0, 1.0)],
)
def test_exact_match_reward(prediction, expected, reward):
    result = exact_match_reward(prediction, expected)

    assert result == reward
    assert isinstance(result, float)


# ---------------------------------------------------------------------------
# against the outputs the probe really recorded (independent evidence, not written by this code)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not PROBE_JSON.exists(), reason="probe evidence file not found")
@pytest.mark.parametrize("section", ["base_evaluation", "candidate_evaluation"])
def test_code_reproduces_the_records_of_the_probe(section):
    records = json.loads(PROBE_JSON.read_text(encoding="utf-8"))[section]["records"]

    assert len(records) == len(EXAMPLES)
    for record, example in zip(records, EXAMPLES, strict=True):
        assert record["question"] == example.question
        assert record["expected"] == example.answer
        assert extract_integer(record["output_text"]) == record["prediction"]
        assert exact_match_reward(record["prediction"], example.answer) == record["reward"]


@pytest.mark.skipif(not PROBE_JSON.exists(), reason="probe evidence file not found")
def test_probe_json_stores_the_same_workload_hash():
    stored = json.loads(PROBE_JSON.read_text(encoding="utf-8"))["workload"]["sha256"]

    assert stored == workload_hash()


# ---------------------------------------------------------------------------
# no heavy dependency: this module must stay usable on a machine without a GPU stack
# ---------------------------------------------------------------------------

def test_importing_the_workload_does_not_import_torch():
    code = "import sys, heteroes.eval.workload; sys.exit(1 if 'torch' in sys.modules else 0)"
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)

    assert result.returncode == 0, result.stderr
