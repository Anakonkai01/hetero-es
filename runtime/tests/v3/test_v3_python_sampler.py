"""
A researcher's sampler (owner 2026-10-22: "người ta tự viết dataloader riêng"): `python@1:<sha>` chooses the rows of each
generation on the coordinator; the frozen context carries them to workers, audits and replays, which only check them.
"""

import json
from pathlib import Path

import pytest

from heteroes.v3 import data as v3data
from heteroes.v3.local import run_local

from test_v3_local import assets, config_for  # noqa: F401  (assets is a fixture)
from test_v3_update_rules import replay

CURRICULUM = """
def curriculum(generation, size, train_rows, seed):
    # the first rows first, one window further each generation
    start = (generation * size) % train_rows
    return [(start + i) % train_rows for i in range(size)]
"""
PYTHON = "python@1:" + "a" * 64


def frozen_context(ledger_path, experiment_id, generation):
    """The context the coordinator froze for a generation (read only; the ledger module itself is not changed)."""
    import sqlite3

    with sqlite3.connect(Path(ledger_path).as_uri() + "?mode=ro", uri=True) as db:
        row = db.execute(
            "SELECT body FROM generation_context WHERE experiment_id=? AND generation=?", (experiment_id, generation)
        ).fetchone()
    return json.loads(row[0]) if row else None


def dataset():
    return v3data.build([{"prompt": f"q{i}"} for i in range(20)], split_seed=1)


def test_a_python_sampler_batch_is_given_and_checked_never_drawn():
    value = dataset()
    with pytest.raises(ValueError, match="comes from the coordinator"):
        v3data.batch(value, 0, 4, 1, PYTHON)
    for bad in ([0, 1, 2], [0, 1, 2, len(value["splits"]["train"])], [0, 1, 2, -1], [0, 1, 2, 3.0], "0123"):
        with pytest.raises(ValueError, match="row numbers"):
            v3data.batch(value, 0, 4, 1, PYTHON, bad)
    chosen = v3data.batch(value, 0, 4, 1, PYTHON, [3, 3, 0, 1])  # repeats are the researcher's choice
    assert chosen["indices"] == [3, 3, 0, 1] and chosen["rows"][0] == chosen["rows"][1]
    with pytest.raises(ValueError, match="only a Python sampler"):
        v3data.batch(value, 0, 4, 1, v3data.SAMPLER, [0, 1, 2, 3])


def test_a_python_sampler_is_researcher_code_pinned_like_a_scorer():
    from heteroes.v3.options import validate_python_code

    config = {"scorer": {"kind": "declarative"}, "coefficientRule": "zscore@1", "sampler": PYTHON}
    with pytest.raises(ValueError, match="sampler pin"):
        validate_python_code({**config, "pythonCode": []})
    from heteroes.v3.scoring import source_sha256

    source = CURRICULUM
    sha = source_sha256("sampler.py", source.encode())
    entry = {"role": "sampler", "name": "sampler.py", "function": "curriculum", "source": source, "codeSha256": sha}
    validate_python_code({**config, "sampler": "python@1:" + sha, "pythonCode": [entry]})


def test_a_run_with_a_python_sampler_freezes_its_rows_and_replays(assets, tmp_path):  # noqa: F811
    (assets / "curriculum.py").write_text(CURRICULUM, encoding="utf-8")
    sampler = {"kind": "python", "path": str(assets / "curriculum.py"), "function": "curriculum"}
    config = config_for(assets, generations=3)
    config["data"] = {**config["data"], "sampler": sampler}
    out = tmp_path / "curriculum"
    summaries = run_local(config, out, workers=2, timeout_seconds=30)  # the workers accepted every context
    recipe = json.loads((out / "recipe.json").read_text())
    from heteroes.v3.scoring import code_sha256

    assert recipe["data"]["batch"]["sampler"] == "python@1:" + code_sha256(assets / "curriculum.py")
    train = len(json.loads((out / "dataset.json").read_text())["splits"]["train"])
    frozen = [frozen_context(out / "ledger.sqlite", "local", g)["batchIndices"] for g in range(3)]
    assert frozen == [[(g * 4 + i) % train for i in range(4)] for g in range(3)]
    children, _, _, _ = replay(out, assets)
    assert children == [s["child_sha256"] for s in summaries]


def test_a_worker_takes_the_coordinators_rows_and_refuses_a_broken_context(assets, tmp_path):  # noqa: F811
    from heteroes.v3.run import RecipeV3Run

    (assets / "curriculum.py").write_text(CURRICULUM, encoding="utf-8")
    config = config_for(assets, generations=1)
    config["data"] = {**config["data"], "sampler": {"kind": "python", "path": str(assets / "curriculum.py"), "function": "curriculum"}}  # fmt: skip
    out = tmp_path / "one"
    run_local(config, out, workers=1, timeout_seconds=30)
    documents = [json.loads((out / f"{n}.json").read_text()) for n in ("recipe", "plan", "dataset")]
    worker = RecipeV3Run(documents[0], documents[1])  # no sampler function: a worker never runs researcher code
    context = frozen_context(out / "ledger.sqlite", "local", 0)
    assert worker.context(documents[2], 0, context["batchIndices"]) == context
    with pytest.raises(ValueError, match="comes from the coordinator"):
        worker.context(documents[2], 0)
    tampered = [*context["batchIndices"][:-1], context["batchIndices"][-1] + 1]
    assert worker.context(documents[2], 0, tampered)["contextHash"] != context["contextHash"]
    # the executor of a worker: it takes the rows from the context and refuses one whose rows do not match its hash
    from types import SimpleNamespace

    from heteroes.executor import CandidateExecutor

    executor = SimpleNamespace(recipe=worker, dataset=documents[2])
    CandidateExecutor.set_generation(executor, 0, context)
    assert executor.batch_rows == [documents[2]["splits"]["train"][i] for i in context["batchIndices"]]
    with pytest.raises(ValueError, match="mismatch"):
        CandidateExecutor.set_generation(executor, 0, {**context, "batchIndices": tampered})
