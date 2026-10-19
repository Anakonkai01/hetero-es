"""Desktop v3 admission must bind repeated texts, signs and exact restore to its reference."""

import copy

import pytest


def test_reference_verification_rejects_text_sign_and_restore_drift():
    from heteroes.product.qualification_v3 import verify

    positive = {
        "recipeHash": "recipe",
        "modelManifestHash": "model",
        "parentSha256": "parent",
        "restoredSha256": "parent",
        "perturbedSha256": "positive",
        "outputsHash": "texts+",
        "reward": 1.0,
    }
    negative = {**positive, "perturbedSha256": "negative", "outputsHash": "texts-"}
    reference = {"expected": positive, "negativeExpected": negative}
    observations = {1: [positive.copy(), positive.copy()], -1: [negative.copy(), negative.copy()]}
    assert verify(reference, observations)["repeatIdentical"]
    for sign in (1, -1):
        for key in positive:
            wrong = copy.deepcopy(observations)
            wrong[sign][0][key] = "drift"
            wrong[sign][1][key] = "drift"
            with pytest.raises(ValueError):
                verify(reference, wrong)
        wrong = copy.deepcopy(observations)
        wrong[sign].pop()
        with pytest.raises(ValueError):
            verify(reference, wrong)
    bad_ref = copy.deepcopy(reference)
    bad_ref["expected"]["restoredSha256"] = "other"
    bad_obs = copy.deepcopy(observations)
    for row in bad_obs[1]:
        row["restoredSha256"] = "other"
    with pytest.raises(ValueError, match="restore"):
        verify(bad_ref, bad_obs)
