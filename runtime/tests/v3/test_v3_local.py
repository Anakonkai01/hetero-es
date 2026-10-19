"""
Recipe v3 experiments on one machine (`heteroes.v3.local`, the CLI and the SDK) with a tiny Qwen2 built offline: the real
coordinator, workers, HTTP protocol, ledger and scoring. Every run is checked independently of the code that ran it: the
stored texts are scored again into the committed rewards, and the recorded updates, replayed by hand on a fresh copy of the
model, give the final weights bit for bit. With a subset or LoRA, the rest of the model never moves.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest
import torch

from heteroes.es.update import apply_coefficients_
from heteroes.eval.candidate import model_weights_sha256
from heteroes.generation_record import GenerationRecord
from heteroes.ledger import Ledger
from heteroes.v3 import data as v3data
from heteroes.v3.local import run_local
from heteroes.v3.model import file_manifest, load, trainable_schema
from heteroes.v3.scoring import code_sha256, score
from tinylm import build_tiny_lm, write_rows

SCORER = """
def distinct_characters(completions, rows):
    return [len(set(text)) / 50 for text in completions]
"""


@pytest.fixture(scope="module")
def assets(tmp_path_factory):
    base = tmp_path_factory.mktemp("tiny")
    build_tiny_lm(base / "model")
    write_rows(base / "rows.jsonl")
    (base / "scorer.py").write_text(SCORER, encoding="utf-8")
    return base


def config_for(assets, **changes):
    config = {
        "model": {"path": str(assets / "model"), "id": "tiny/qwen2"},
        "data": {"path": str(assets / "rows.jsonl"), "promptField": "question", "batchSize": 4, "batchSeed": 3},
        "weightSpace": {"kind": "full"},
        "sigma": {"initial": 0.5},
        "maxNewTokens": 8,
        "population": 4,
        "generations": 2,
        "alpha": 0.5,
        "scorer": {
            "kind": "python",
            "name": "distinct-characters",
            "version": 1,
            "path": str(assets / "scorer.py"),
            "function": "distinct_characters",
        },
    }
    config.update(changes)
    return config


def check_run(out, assets, experiment_id="local"):
    """Re-score the stored texts and replay the recorded updates on a fresh model; returns the replayed child."""
    recipe = json.loads((out / "recipe.json").read_text())
    plan = json.loads((out / "plan.json").read_text())
    dataset = json.loads((out / "dataset.json").read_text())
    assert plan["scorer"]["codeSha256"] == code_sha256(assets / "scorer.py")
    model, _ = load(assets / "model", file_manifest(assets / "model"))
    adapter = out / "initial-adapter.bin"
    schema = trainable_schema(model, recipe["weightSpace"], adapter if adapter.exists() else None)
    assert schema.hash == recipe["schemaHash"]
    namespace = {}
    exec(SCORER, namespace)
    with Ledger(out / "ledger.sqlite") as ledger:
        children = []
        for generation in range(plan["generations"]):
            rows = v3data.batch(dataset, generation, recipe["data"]["batch"]["size"], recipe["data"]["batch"]["seed"])[
                "rows"
            ]
            for candidate in ledger.list_candidates(experiment_id, generation):
                _, texts = ledger.get_completions(candidate.descriptor.candidate_id)
                assert len(texts) == len(rows)
                assert (
                    candidate.result.reward == score(plan["scorer"], texts, rows, namespace["distinct_characters"])[0]
                )
            stored = ledger.get_update(experiment_id, generation)
            assert isinstance(stored.record, GenerationRecord) and stored.record.coefficient_rule == "zscore@1"
            stored.record.verify_coefficients(plan["coefficientRule"]["eta"])
            seeds, coefficients = stored.record.update_inputs()
            apply_coefficients_(
                model, schema, seeds, coefficients, stored.record.alpha, recipe["noise"]["chunkElements"]
            )
            assert model_weights_sha256(model, schema) == stored.child_weights_sha256
            children.append(stored.child_weights_sha256)
    return model, schema, children


@pytest.mark.parametrize(
    "space, antithetic",
    [
        ({"kind": "full"}, True),
        ({"kind": "subset", "include": [r"layers\.1\."]}, False),
        ({"kind": "lora", "rank": 2, "alpha": 4, "targetModules": ["q_proj", "v_proj"], "adapterSeed": 5}, True),
    ],
)
def test_a_local_run_replays_bit_for_bit_and_scores_its_stored_texts(assets, tmp_path, space, antithetic):
    out = tmp_path / "run"
    summaries = run_local(
        config_for(assets, weightSpace=space, antithetic=antithetic), out, workers=2, timeout_seconds=30
    )
    assert [s["generation"] for s in summaries] == [0, 1]
    assert not all(s["noop"] for s in summaries)  # premise: the weights did move
    model, schema, children = check_run(out, assets)
    assert children == [s["child_sha256"] for s in summaries]
    with Ledger(out / "ledger.sqlite") as ledger:
        signs = ledger.get_generation_results("local", 0).signs
    assert signs == ((1, -1, 1, -1) if antithetic else (1, 1, 1, 1))
    if space["kind"] != "full":  # the base never moves: compare with a fresh load, outside the trainable schema
        fresh, _ = load(assets / "model", file_manifest(assets / "model"))
        trained = set(entry.canonical_name for entry in schema.entries)
        base = dict(fresh.named_parameters())
        for name, parameter in model.named_parameters():
            if name not in trained and name in base:
                assert torch.equal(parameter.view(torch.int16), base[name].view(torch.int16)), name


def test_a_declarative_scorer_needs_no_code(assets, tmp_path):
    scorer = {
        "kind": "declarative",
        "name": "exact-string",
        "config": {"answerField": "answer", "strip": True, "casefold": True},
    }
    summaries = run_local(config_for(assets, scorer=scorer, generations=1), tmp_path / "run", timeout_seconds=30)
    plan = json.loads((tmp_path / "run" / "plan.json").read_text())
    assert plan["scorer"]["codeSha256"] is None and len(summaries) == 1


def test_the_command_line_runs_a_spec_with_relative_paths(assets, tmp_path):
    spec = config_for(assets, generations=1)
    spec["data"]["path"] = "rows.jsonl"
    (tmp_path / "rows.jsonl").write_text((assets / "rows.jsonl").read_text())
    (tmp_path / "spec.json").write_text(json.dumps(spec))
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "heteroes.v3",
            "run",
            str(tmp_path / "spec.json"),
            "--out",
            str(tmp_path / "run"),
            "--timeout-seconds",
            "30",
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.startswith("generation 0: mean reward")


def test_the_sdk_trains_with_a_reward_function_from_a_file(assets, tmp_path, monkeypatch):
    from heteroes.sdk import ESConfig, ESTrainer

    module = tmp_path / "my_reward.py"
    module.write_text(
        "from heteroes.sdk import reward\n\n\n@reward('distinct@2')\ndef distinct(completions, rows):\n"
        "    return [len(set(text)) / 50 for text in completions]\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    import my_reward

    args = ESConfig(
        model_path=str(assets / "model"),
        model_id="tiny/qwen2",
        train_dataset=str(assets / "rows.jsonl"),
        prompt_field="question",
        population=4,
        generations=1,
        sigma=0.5,
        alpha=0.5,
        batch_size=4,
        max_new_tokens=8,
    )
    trainer = ESTrainer(args, reward_func=my_reward.distinct)
    assert trainer.scorer["name"] == "distinct" and trainer.scorer["version"] == 2
    trainer.train(tmp_path / "run", timeout_seconds=30)
    plan = json.loads((tmp_path / "run" / "plan.json").read_text())
    assert plan["scorer"]["codeSha256"] == code_sha256(module) and plan["scorer"]["name"] == "distinct"


def test_the_sdk_refuses_rewards_it_cannot_pin(assets):
    from heteroes.sdk import ESConfig, ESTrainer, reward

    args = ESConfig(model_path="m", model_id="x", train_dataset="d")
    with pytest.raises(ValueError):
        ESTrainer(args, reward_func=lambda completions, rows: [0.0] * len(rows))
    with pytest.raises(ValueError):
        ESTrainer(args)
    with pytest.raises(ValueError):
        ESTrainer(args, reward_func=check_run, scorer={"name": "exact-string"})
    with pytest.raises(ValueError):
        reward("no-version")
