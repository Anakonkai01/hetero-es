"""Python rewards on the web lab (owner 2026-10-20): frozen code, coordinator-only, in a child process with a time limit."""

import pytest

from heteroes.product.v3 import prepare_run, python_functions
from heteroes.v3.options import validate_options
from heteroes.v3.sandbox import ChildFunction
from heteroes.v3.scoring import ScorerError, code_sha256, source_sha256

SCORER = """
import time

def reward(texts, rows):
    print("researcher output goes to stderr")
    if texts and texts[0] == "hang":
        time.sleep(60)
    if texts and texts[0] == "crash":
        import os
        os._exit(3)
    if texts and texts[0] == "token":
        import os
        return [float("HETEROES_TOKEN" in os.environ)]
    if texts and texts[0] == "raise":
        raise KeyError("answer")
    return [float(t == r["answer"]) for t, r in zip(texts, rows)]
"""
RULE = """
import numpy as np

def coefficients(rewards):
    values = np.asarray(rewards, dtype=np.float32)
    return values - values.mean()
"""


def entry(role, name, function, source):
    return {
        "role": role,
        "name": name,
        "function": function,
        "source": source,
        "codeSha256": source_sha256(name, source.encode()),
    }


def config(**changes):
    scorer = entry("scorer", "reward.py", "reward", SCORER)
    rule = entry("coefficients", "rule.py", "coefficients", RULE)
    base = {
        "weightSpace": {"kind": "full"},
        "scorer": {
            "kind": "python",
            "name": "my-reward",
            "version": 1,
            "codeSha256": scorer["codeSha256"],
            "config": {},
        },
        "coefficientRule": "python@1:" + rule["codeSha256"],
        "antithetic": False,
        "candidatesPerGeneration": 4,
        "decodeEngine": "hf_generate",
        "systemPrompt": None,
        "alpha": 0.001,
        "pythonCode": [scorer, rule],
    }
    return {**base, **changes}


def test_the_hash_of_an_uploaded_file_is_the_hash_the_cli_gives_the_same_file(tmp_path):
    (tmp_path / "reward.py").write_text(SCORER)
    assert source_sha256("reward.py", SCORER.encode()) == code_sha256(tmp_path / "reward.py")


def test_a_lab_configuration_carries_exactly_the_code_its_plan_pins():
    validate_options(config(), allow_python=True)
    with pytest.raises(ValueError, match="declarative"):
        validate_options(config())  # a lab that does not allow Python
    good = config()
    tampered = [{**good["pythonCode"][0], "source": SCORER + "\n# changed"}, good["pythonCode"][1]]
    for changes in (
        {"pythonCode": tampered},
        {"pythonCode": good["pythonCode"][:1]},  # the rule's code is missing
        {"pythonCode": good["pythonCode"] * 2},
        {"coefficientRule": "zscore@1"},  # code the plan does not use
        {"pythonCode": [{**good["pythonCode"][0], "function": "not an identifier"}, good["pythonCode"][1]]},
    ):
        with pytest.raises(ValueError):
            validate_options(config(**changes), allow_python=True)
    worker = {k: v for k, v in good.items() if k != "pythonCode"}
    validate_options(worker, allow_python=True, with_code=False)  # a worker knows the spec, never the code
    with pytest.raises(ValueError, match="may not carry"):
        validate_options(good, allow_python=True, with_code=False)


def test_a_worker_refuses_a_configuration_that_carries_code(tmp_path):
    with pytest.raises(ValueError, match="never receives researcher code"):
        prepare_run(config(), tmp_path, "cpu", declared={})


def test_the_coordinator_runs_the_frozen_code_in_a_child_process(tmp_path, capfd, monkeypatch):
    monkeypatch.setenv("HETEROES_TOKEN", "coordinator-secret")
    scorer, rule, sampler = python_functions(config(pythonTimeoutSeconds=5), tmp_path)
    assert sampler is None  # this experiment pins no sampler
    try:
        assert scorer(["token"], [{"answer": "x"}]) == [0.0]  # the child never sees the coordinator's credentials
        assert scorer(["4", "5"], [{"answer": "4"}, {"answer": "4"}]) == [1.0, 0.0]
        assert rule([1.0, 3.0]) == [-1.0, 1.0]  # a numpy array comes back as numbers
        assert "researcher output goes to stderr" in capfd.readouterr().err
        with pytest.raises(ScorerError, match="KeyError"):
            scorer(["raise"], [{"answer": "x"}])
        with pytest.raises(ScorerError, match="ended"):
            scorer(["crash"], [{"answer": "x"}])
        with pytest.raises(ScorerError, match="more than 5 s"):
            scorer(["hang"], [{"answer": "x"}])
        assert scorer(["4"], [{"answer": "4"}]) == [1.0]  # a new child after a failure
    finally:
        scorer.close()
        rule.close()


def test_frozen_code_that_changed_on_disk_or_in_transit_is_refused(tmp_path):
    bad = config()
    bad["pythonCode"][0] = {**bad["pythonCode"][0], "source": "def reward(t, r):\n    return [0.0] * len(t)\n"}
    with pytest.raises(ValueError, match="changed"):
        python_functions(bad, tmp_path)


def test_a_missing_function_is_a_loud_failure(tmp_path):
    (tmp_path / "reward.py").write_text(SCORER)
    function = ChildFunction(tmp_path / "reward.py", "absent", timeout=5, error=ScorerError)
    with pytest.raises(ScorerError, match="ended"):
        function([], [])


def test_a_recovery_point_of_a_python_scored_plan_is_accepted():
    from heteroes.v3.recovery import validate_state
    from heteroes.v3.run import RecipeV3Run
    from test_v3_data_run import documents

    spec = {"kind": "python", "name": "my-reward", "version": 1, "codeSha256": "a" * 64, "config": {}}
    recipe, plan, dataset = documents(scorer=spec)
    run = RecipeV3Run(recipe, plan)
    row = {"recipeHash": run.hash, "planHash": run.plan_hash, "generation": -1, "weightsSha256": "b" * 64,
           "meanReward": 0.5}  # fmt: skip
    state = {"recipe": recipe, "plan": plan, "dataset": dataset, "validation": [row],
             "selection": {**row, "validationReward": 0.5}}  # fmt: skip
    config = {"datasetIdentity": {k: dataset[k] for k in ("contentHash", "splitHashes")}}
    assert validate_state(state, config, recipe, 0, {f"selection/{'b' * 64}.bin": {}}).plan_hash == run.plan_hash
