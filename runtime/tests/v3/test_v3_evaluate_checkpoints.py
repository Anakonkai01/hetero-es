"""runtime/scripts/v3_evaluate_checkpoints.py: rebuild checkpoints of a local v3 run by replay and score a split."""

import importlib.util
import json
from pathlib import Path

import pytest

from heteroes.study.evaluation import generate_rows
from heteroes.v3.local import run_local
from heteroes.v3.model import file_manifest, load
from heteroes.v3.scoring import score

from test_v3_local import assets, config_for  # noqa: F401  (assets is a fixture)


def tool():
    path = Path(__file__).resolve().parents[2] / "scripts" / "v3_evaluate_checkpoints.py"
    spec = importlib.util.spec_from_file_location("v3_evaluate_checkpoints", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SCORER = {
    "kind": "declarative",
    "name": "exact-string",
    "config": {"answerField": "answer", "strip": True, "casefold": True},
}


def test_checkpoints_are_rebuilt_by_replay_and_scored(assets, tmp_path):  # noqa: F811
    out = tmp_path / "run"
    summaries = run_local(config_for(assets, generations=3), out, workers=1, timeout_seconds=30)
    assert any(not s["noop"] for s in summaries)
    module = tool()
    with pytest.raises(ValueError, match="scorer"):
        module.evaluate(out, assets / "model", [0], "validation", device="cpu")
    report = module.evaluate(
        out, assets / "model", [-1, 0, 2], "validation", "cpu", assets / "scorer.py", "distinct_characters"
    )
    assert [r["generation"] for r in report["checkpoints"]] == [-1, 0, 2]
    assert [r["weightsSha256"] for r in report["checkpoints"][1:]] == [
        summaries[0]["child_sha256"],
        summaries[2]["child_sha256"],
    ]
    # the base checkpoint is the untouched model, evaluated the same way
    dataset = json.loads((out / "dataset.json").read_text())
    rows = dataset["splits"]["validation"]
    model, tokenizer = load(assets / "model", file_manifest(assets / "model"))
    raw = generate_rows(model.float(), tokenizer, rows, {"systemPrompt": None, "maxNewTokens": 8}, 16)
    plan = json.loads((out / "plan.json").read_text())
    base = report["checkpoints"][0]
    namespace = {}
    exec((assets / "scorer.py").read_text(), namespace)
    expected = score(plan["scorer"], [r["output"] for r in raw], rows, namespace["distinct_characters"])[0]
    assert base["meanReward"] == expected
    assert report["checkpoints"][2]["outputs"] != base["outputs"]  # premise: the weights changed the answers
    assert base["outputs"] == [r["output"] for r in raw] and base["count"] == len(rows)
    assert set(base) >= {"scoreCounts", "truncated", "meanCharacters"}


def test_a_wrong_record_chain_is_refused(assets, tmp_path):  # noqa: F811
    out = tmp_path / "run"
    run_local(config_for(assets, scorer=SCORER, generations=1), out, workers=1, timeout_seconds=30)
    module = tool()
    with pytest.raises(ValueError, match="generation"):
        module.evaluate(out, assets / "model", [3], "validation", device="cpu")
    with pytest.raises(ValueError, match="split"):
        module.evaluate(out, assets / "model", [0], "everything", device="cpu")


def test_a_replay_that_does_not_reach_the_recorded_child_is_refused(assets, tmp_path, monkeypatch):  # noqa: F811
    out = tmp_path / "run"
    summaries = run_local(config_for(assets, generations=1), out, workers=1, timeout_seconds=30)
    assert not summaries[0]["noop"]  # premise: the recorded child differs from the base
    monkeypatch.setattr("heteroes.es.update.apply_coefficients_", lambda *args, **kwargs: None)
    with pytest.raises(ValueError, match="does not hash"):
        tool().evaluate(out, assets / "model", [0], "validation", "cpu", assets / "scorer.py", "distinct_characters")
