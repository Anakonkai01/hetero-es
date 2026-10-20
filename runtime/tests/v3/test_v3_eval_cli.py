"""Paired comparison, independent sample metrics and the public evaluation command."""

import copy
import json
import math

import pytest


def report(scores, rows_hash="a" * 64):
    return {
        "rowsHash": rows_hash,
        "scorer": {"kind": "test"},
        "checkpoints": [{"generation": 0, "scores": scores, "count": len(scores), "split": "test"}],
    }


def test_compare_pairs_rows_and_uses_two_sided_exact_binomial():
    from heteroes.v3.comparison import compare

    a = report([1, 0, 0, 0, 0, 0, 1])
    b = report([0, 1, 1, 1, 1, 0, 1])
    result = compare(a, b, resamples=2000, seed=17)
    assert result["fixed"] == 4 and result["broke"] == 1
    assert result["bothCorrect"] == 1 and result["bothWrong"] == 1
    assert result["difference"] == pytest.approx(3 / 7)
    assert result["mcnemarExactP"] == pytest.approx(0.375)
    assert result == compare(a, b, resamples=2000, seed=17)
    assert compare(a, a)["bootstrapCI"] == [0.0, 0.0]
    assert compare(report([0] * 4), report([1] * 4))["bootstrapCI"] == [1.0, 1.0]
    assert compare(report([0] * 4), report([1] * 4))["mcnemarExactP"] == pytest.approx(0.125)
    assert compare(report([0.1, 0.5]), report([0.2, 1]))["difference"] == pytest.approx(0.3)


def test_exact_mcnemar_matches_small_integer_binomial_oracle_and_handles_large_counts():
    from heteroes.v3.comparison import mcnemar_exact

    for n in range(25):
        for fixed in range(n + 1):
            broke = n - fixed
            expected = min(1, 2 * sum(math.comb(n, i) for i in range(min(fixed, broke) + 1)) / 2**n)
            assert mcnemar_exact(fixed, broke) == pytest.approx(expected, abs=1e-12)
    assert mcnemar_exact(1_000_000, 0) == 0
    assert mcnemar_exact(500_000, 500_000) == 1
    assert 0 < mcnemar_exact(500_000, 499_000) < 1


@pytest.mark.parametrize("change", ["rows", "scorer", "count", "nan", "bool", "missing"])
def test_compare_refuses_unpaired_or_malformed_reports(change):
    from heteroes.v3.comparison import compare

    a, b = report([0, 1]), report([1, 0])
    if change == "rows":
        b["rowsHash"] = "b" * 64
    elif change == "scorer":
        b["scorer"] = {"kind": "other"}
    elif change == "count":
        b["checkpoints"][0]["scores"].pop()
    elif change == "nan":
        b["checkpoints"][0]["scores"][0] = float("nan")
    elif change == "bool":
        b["checkpoints"][0]["scores"][0] = True
    else:
        b.pop("rowsHash")
    with pytest.raises(ValueError):
        compare(a, b)


def test_sampled_metrics_vote_on_extracted_answers_with_a_fixed_tie_rule():
    from heteroes.v3.evaluation import sample_metrics

    scorer = {"kind": "declarative", "name": "last-integer", "version": 1, "codeSha256": None, "config": {}}
    texts = [["reason 1; answer 2", "reason 2; answer 2", "wrong 3", "unparsed"]]
    result = sample_metrics(texts, [{"answer": 2}], scorer, ks=[1, 2, 4])
    row = result["rows"][0]
    assert row["correct"] == 2 and row["majorityAnswer"] == "2" and row["majorityCorrect"] is True
    assert row["passAtK"] == {"1": 0.5, "2": pytest.approx(5 / 6), "4": 1.0}
    tie = sample_metrics([["3", "2"]], [{"answer": 2}], scorer, ks=[1])
    assert tie["rows"][0]["majorityAnswer"] == "2"
    invalid = sample_metrics([["none", "no answer"]], [{"answer": 2}], scorer, ks=[1])
    assert invalid["rows"][0]["majorityAnswer"] is None
    assert invalid["majorityAccuracy"] == 0
    with pytest.raises(ValueError):
        sample_metrics(texts, [{"answer": 2}], scorer, ks=[5])


def test_cli_evaluation_replays_and_samples_with_pinned_seeds(assets, tmp_path):
    from test_v3_local import config_for
    from heteroes.v3.local import run_local
    from heteroes.v3.__main__ import main

    scorer = {"kind": "declarative", "name": "last-integer", "config": {}}
    out = tmp_path / "run"
    summaries = run_local(
        config_for(assets, scorer=scorer, generations=1), out, experiment_id="custom-experiment", timeout_seconds=30
    )
    target = tmp_path / "eval.json"
    arguments = [
        "eval",
        str(out),
        "--model-path",
        str(assets / "model"),
        "--generations=0",
        "--split",
        "test",
        "--samples",
        "3",
        "--ks",
        "1,3",
        "--seed",
        "18",
        "--out",
        str(target),
    ]
    assert main(arguments) == 0
    result = json.loads(target.read_text())
    checkpoint = result["checkpoints"][0]
    assert checkpoint["weightsSha256"] == summaries[0]["child_sha256"]
    assert len(checkpoint["scores"]) == checkpoint["count"]
    assert checkpoint["sampled"]["samplesPerRow"] == 3
    assert result["sampling"]["seed"] == 18 and len(result["rowsHash"]) == 64
    assert len(checkpoint["sampled"]["rows"][0]["outputs"]) == 3
    second = tmp_path / "repeat.json"
    assert main([*arguments[:-1], str(second)]) == 0
    repeated = json.loads(second.read_text())
    assert repeated["checkpoints"] == result["checkpoints"]
    compared = tmp_path / "compare.json"
    assert main(["compare", str(target), str(second), "--out", str(compared)]) == 0
    assert json.loads(compared.read_text())["difference"] == 0
    with pytest.raises((SystemExit, FileExistsError)):
        main(arguments)


from test_v3_local import assets  # noqa: E402,F401
