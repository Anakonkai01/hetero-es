"""Re-run the same candidate draws on another resource layout without reusing a run/ledger identity."""

import json

import pytest

from heteroes.ledger import Ledger
from heteroes.manifest import derive_seed
from heteroes.v3.local import run_local
from test_v3_local import assets, config_for  # noqa: F401


@pytest.mark.parametrize("antithetic", [False, True])
def test_an_explicit_namespace_reproduces_candidates_across_run_ids_and_worker_counts(assets, tmp_path, antithetic):
    config = config_for(assets, antithetic=antithetic)
    baseline_id, repeat_id = "baseline", "repeat"
    baseline = run_local(config, tmp_path / "one", experiment_id=baseline_id, workers=1, timeout_seconds=30)
    repeated = run_local(
        {**config, "candidateSeedNamespace": baseline_id},
        tmp_path / "two",
        experiment_id=repeat_id,
        workers=2,
        timeout_seconds=30,
    )
    assert any(not summary["noop"] for summary in baseline)
    assert [s["child_sha256"] for s in baseline] == [s["child_sha256"] for s in repeated]
    assert [s["rewards"] for s in baseline] == [s["rewards"] for s in repeated]
    for name in ("recipe.json", "plan.json"):
        assert json.loads((tmp_path / "one" / name).read_text()) == json.loads((tmp_path / "two" / name).read_text())
    with Ledger(tmp_path / "one" / "ledger.sqlite") as one, Ledger(tmp_path / "two" / "ledger.sqlite") as two:
        for generation in range(2):
            first = one.get_update(baseline_id, generation).record
            second = two.get_update(repeat_id, generation).record
            assert first.seeds == second.seeds
            assert first.hash != second.hash  # each run retains its own ledger identity
            expected = tuple(derive_seed(baseline_id, generation, i // 2 if antithetic else i) for i in range(4))
            assert first.seeds == expected  # the old default stays bit-identical


def test_the_sdk_and_managed_options_keep_the_optional_namespace():
    from heteroes.sdk import ESConfig
    from heteroes.v3.options import validate_seed_namespace

    base = dict(model_path="m", model_id="m", train_dataset="d.jsonl")
    assert "candidateSeedNamespace" not in ESConfig(**base).to_config({})
    assert ESConfig(**base, candidate_seed_namespace="baseline").to_config({})["candidateSeedNamespace"] == "baseline"
    for valid in (None, "baseline", "a" * 32, "run:2026-10-20", "x" * 128):
        validate_seed_namespace(valid)
    for invalid in ("", " ", "x" * 129, 1, False, [], "a\nb", "name with spaces"):
        with pytest.raises(ValueError, match="seed namespace"):
            validate_seed_namespace(invalid)
