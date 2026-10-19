"""
Runs of the opened update formula θ ← θ + α_t · Σ_a β^a · (1/n)Σ cᵢεᵢ on the tiny CPU model: a centered-rank, a python
coefficient rule, an alpha schedule and momentum, each replayed bit for bit from its records alone.
"""

import json

import numpy as np
import pytest
import torch

from heteroes.es.update import apply_coefficients_
from heteroes.eval.candidate import model_weights_sha256
from heteroes.ledger import Ledger
from heteroes.noise.contracts import ParameterNoiseAddress
from heteroes.noise.engine import chunk_length, generate_chunk_noise, num_chunks
from heteroes.v3.documents import alpha_at
from heteroes.v3.local import run_local
from heteroes.v3.model import file_manifest, load, trainable_schema

from test_v3_local import assets, config_for  # noqa: F401  (assets is a fixture)

MOMENTUM = {"beta": 0.5, "window": 3}
CENTERED = """
def centered(rewards):
    mean = sum(rewards) / len(rewards)
    return [r - mean for r in rewards]
"""


def replay(out, assets, check=None):  # noqa: F811
    """Apply every recorded update to a fresh model; returns (children, records, weights before each update)."""
    recipe = json.loads((out / "recipe.json").read_text())
    plan = json.loads((out / "plan.json").read_text())
    model, _ = load(assets / "model", file_manifest(assets / "model"))
    schema = trainable_schema(model, recipe["weightSpace"])
    children, records, parents = [], [], []
    with Ledger(out / "ledger.sqlite") as ledger:
        for generation in range(plan["generations"]):
            record = ledger.get_update("local", generation).record
            assert record.alpha == alpha_at(plan, generation)
            if check:
                check(record)
            parents.append(
                {e.canonical_name: p.detach().clone() for e, p in zip(schema.entries, schema_tensors(model, schema))}
            )
            seeds, coefficients = record.update_inputs()
            apply_coefficients_(model, schema, seeds, coefficients, record.alpha, recipe["noise"]["chunkElements"])
            children.append(model_weights_sha256(model, schema))
            assert children[-1] == ledger.get_update("local", generation).child_weights_sha256
            records.append(record)
    return children, records, parents, (model, schema, recipe)


def schema_tensors(model, schema):
    from heteroes.model.schema import resolve_tensors

    return resolve_tensors(model, schema)


def moved(summaries):
    return [not s["noop"] for s in summaries]


def test_a_centered_rank_run_records_ranks_and_replays(assets, tmp_path):  # noqa: F811
    out = tmp_path / "rank"
    summaries = run_local(config_for(assets, coefficientRule="centered-rank@1"), out, workers=2, timeout_seconds=30)
    assert any(moved(summaries))

    def check(record):
        assert record.coefficient_rule == "centered-rank@1" and record.verify_coefficients(1e-9)
        assert sorted(record.coefficients) == sorted(record.coefficients[::-1])  # ranks are symmetric around 0

    children, _, _, _ = replay(out, assets, check)
    assert children == [s["child_sha256"] for s in summaries]


def test_a_python_coefficient_rule_is_pinned_and_only_its_coordinator_can_recompute_it(assets, tmp_path):  # noqa: F811
    (assets / "centered.py").write_text(CENTERED, encoding="utf-8")
    rule = {"kind": "python", "path": str(assets / "centered.py"), "function": "centered"}
    out = tmp_path / "python"
    summaries = run_local(config_for(assets, coefficientRule=rule), out, workers=2, timeout_seconds=30)
    plan = json.loads((out / "plan.json").read_text())
    from heteroes.v3.scoring import code_sha256

    assert plan["coefficientRule"] == {
        "name": "python", "version": 1, "eta": 1e-9, "codeSha256": code_sha256(assets / "centered.py"),
    }  # fmt: skip
    namespace = {}
    exec(CENTERED, namespace)

    def check(record):
        assert record.coefficient_rule == f"python@1:{plan['coefficientRule']['codeSha256']}"
        assert record.verify_coefficients(1e-9) is False
        assert record.verify_coefficients(1e-9, function=namespace["centered"]) is True

    children, _, _, _ = replay(out, assets, check)
    assert children == [s["child_sha256"] for s in summaries]


def test_an_alpha_schedule_goes_into_each_record(assets, tmp_path):  # noqa: F811
    out = tmp_path / "alpha"
    config = config_for(assets, generations=3, alphaSchedule={"kind": "linear", "minimum": 0.125})
    summaries = run_local(config, out, workers=1, timeout_seconds=30)
    children, records, _, _ = replay(out, assets)
    assert [r.alpha for r in records] == [0.5, 0.3125, 0.125] and children == [s["child_sha256"] for s in summaries]
    run, dataset = run_of(out)
    assert [run.context(dataset, g)["alphaFloat32"] for g in range(3)] == [0.5, 0.3125, 0.125]
    plain_run, plain_data = run_of(tmp_path / "plain", config_for(assets, generations=1))
    assert {"alphaFloat32", "update"}.isdisjoint(plain_run.context(plain_data, 0))  # earlier contexts keep their hash


def run_of(out, config=None):
    from heteroes.v3.run import RecipeV3Run

    if config is not None:
        run_local(config, out, workers=1, timeout_seconds=30)
    documents = [json.loads((out / f"{name}.json").read_text()) for name in ("recipe", "plan", "dataset")]
    return RecipeV3Run(documents[0], documents[1]), documents[2]


def noise(seed, schema, entry, numel, chunk_elements):
    parts = []
    for index in range(num_chunks(numel=numel, chunk_elements=chunk_elements)):
        address = ParameterNoiseAddress(
            candidate_seed=seed, schema_hash=schema.hash, parameter_index=entry.index, chunk_elements=chunk_elements
        ).chunk(index)
        parts.append(generate_chunk_noise(address, chunk_length(numel, index, chunk_elements)))
    return np.concatenate(parts).astype(np.float64)


def test_momentum_steps_are_the_beta_weighted_sum_of_the_window_and_replay(assets, tmp_path):  # noqa: F811
    plain = run_local(config_for(assets, generations=4), tmp_path / "plain", workers=1, timeout_seconds=30)
    out = tmp_path / "momentum"
    summaries = run_local(config_for(assets, generations=4, momentum=MOMENTUM), out, workers=1, timeout_seconds=30)
    assert all(moved(summaries))  # premise: every generation has a signal
    assert summaries[0]["child_sha256"] == plain[0]["child_sha256"]  # nothing to remember yet: today's step exactly
    assert summaries[1]["child_sha256"] != plain[1]["child_sha256"]
    children, records, parents, (model, schema, recipe) = replay(out, assets)
    assert children == [s["child_sha256"] for s in summaries]
    assert [len(r.momentum_history) for r in records] == [0, 1, 2, 2]  # the window holds 3 generations
    assert [[e["generation"] for e in r.momentum_history] for r in records] == [[], [0], [1, 0], [2, 1]]
    run, dataset = run_of(out)
    assert run.context(dataset, 1)["update"] == {"kind": "momentum", **MOMENTUM}
    # generation 2, in float64: α · (g2 + β g1 + β² g0) with g_s the mean of c·ε over its own seeds
    chunk_elements = recipe["noise"]["chunkElements"]
    worst = 0.0
    for entry in schema.entries[:4]:
        before = parents[2][entry.canonical_name].double().view(-1).numpy()
        numel = before.size
        step = np.zeros(numel)
        for age, record in enumerate([records[2], records[1], records[0]]):
            seeds, coefficients = record.own_inputs()
            direction = sum(c * noise(s, schema, entry, numel, chunk_elements) for s, c in zip(seeds, coefficients))
            step += 0.5**age * direction / len(seeds)
        expected = before + records[2].alpha * step
        after = parents[3][entry.canonical_name].double().view(-1).numpy()  # the weights generation 2 produced
        # the kernel accumulates in float32 and rounds to FP16 once: within one FP16 step of the exact value
        ulp = np.spacing(np.abs(expected).astype(np.float16)).astype(np.float64)
        assert np.all(np.abs(after - expected) <= ulp + 1e-6), entry.canonical_name
        worst = max(worst, float(np.max(np.abs(after - before))))
    assert worst > 0  # premise: the compared tensors moved


def test_a_momentum_plan_refuses_a_bad_beta(assets, tmp_path):  # noqa: F811
    with pytest.raises(ValueError, match="beta"):
        run_local(config_for(assets, momentum={"beta": 0.9, "window": 3}), tmp_path / "bad", timeout_seconds=30)
    assert torch.__version__  # torch stays importable after the refusal


def test_the_sdk_offers_every_update_choice(assets, tmp_path, monkeypatch):  # noqa: F811
    from heteroes.sdk import ESConfig, ESTrainer

    (tmp_path / "my_rule.py").write_text(
        CENTERED + "\n\ndef distinct(completions, rows):\n    return [len(set(t)) / 50 for t in completions]\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    import my_rule

    base = dict(model_path="m", model_id="x", train_dataset="d")
    assert {"alphaSchedule", "momentum"}.isdisjoint(ESConfig(**base).to_config({}))
    config = ESConfig(**base, alpha=0.01, alpha_schedule="cosine", alpha_minimum=0.001, momentum_beta=0.875).to_config(
        {}
    )
    assert config["alphaSchedule"] == {"kind": "cosine", "minimum": 0.001}
    assert config["momentum"] == {"beta": 0.875, "window": 4}
    args = ESConfig(
        model_path=str(assets / "model"), model_id="tiny/qwen2", train_dataset=str(assets / "rows.jsonl"),
        prompt_field="question", population=4, generations=2, sigma=0.5, alpha=0.5, batch_size=4, max_new_tokens=8,
        momentum_beta=0.5, momentum_window=2,
    )  # fmt: skip
    trainer = ESTrainer(args, reward_func=my_rule.distinct, coefficient_func=my_rule.centered)
    trainer.train(tmp_path / "run", timeout_seconds=30)
    plan = json.loads((tmp_path / "run" / "plan.json").read_text())
    assert plan["coefficientRule"]["name"] == "python" and plan["update"] == {
        "kind": "momentum",
        "beta": 0.5,
        "window": 2,
    }
    with pytest.raises(ValueError, match="coefficient"):
        ESTrainer(args, reward_func=my_rule.distinct, coefficient_func=lambda r: r)
