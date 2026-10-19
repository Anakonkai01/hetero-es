import pytest
from heteroes.product.qualification import verify


def test_qualification_rejects_reward_or_weight_drift_and_false_restore():
    reference = {
        "recipeHash": "recipe",
        "parentSha256": "parent",
        "perturbedSha256": "candidate",
        "restoredSha256": "parent",
        "reward": 0.1875,
    }
    assert verify(reference, [dict(reference), dict(reference)])["passed"]
    for key in reference:
        changed = {**reference, key: "wrong"}
        with pytest.raises(ValueError):
            verify(reference, [changed, changed])
    with pytest.raises(ValueError):
        verify(reference, [reference, {**reference, "reward": 0.25}])
    with pytest.raises(ValueError):
        verify(reference, [reference])


def test_prediction_probe_rejects_different_texts_with_identical_reward():
    import hashlib
    import json
    from heteroes.product.qualification import verify_prediction

    outputs = [str(i) for i in range(16)]
    reference = {
        "outputs": outputs,
        "outputsSha256": hashlib.sha256(json.dumps(outputs, separators=(",", ":")).encode()).hexdigest(),
        "reward": 0.3125,
    }
    observed = {"outputs": outputs, "reward": 0.3125, "parentSha256": "parent", "restoredSha256": "parent"}
    assert verify_prediction(reference, observed)["predictionProbePassed"]
    with pytest.raises(ValueError):
        verify_prediction(reference, {**observed, "outputs": ["wrong"] + outputs[1:]})
    with pytest.raises(ValueError):
        verify_prediction(reference, {**observed, "reward": 0.25})
    with pytest.raises(ValueError):
        verify_prediction(reference, {**observed, "restoredSha256": "wrong"})
