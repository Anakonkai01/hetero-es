"""A lab can establish and reproduce a reference for a newly registered model, without making worker adapters."""

import copy
import subprocess
import sys

import pytest

from heteroes.canonical import canonical_json_hash
from heteroes.product.model_qualification import build_reference, check_reference, qualify
from heteroes.v3.model import registration_manifest
from tinylm import build_tiny_lm


@pytest.fixture(scope="module")
def new_model(tmp_path_factory):
    root = tmp_path_factory.mktemp("new-model-qualification")
    build_tiny_lm(root)
    manifest = registration_manifest(root, "research/new-model", "e" * 40)
    return root, manifest


def test_a_new_model_reference_round_trips_and_never_initializes_worker_adapters(new_model, monkeypatch):
    import heteroes.model.lora as lora

    def refuse(*args, **kwargs):
        raise AssertionError("workers never initialize an adapter")

    monkeypatch.setattr(lora, "create_initial_adapter", refuse)
    root, manifest = new_model
    reference, observations = build_reference(root, manifest, device="cpu")
    assert check_reference(reference, manifest) is reference
    assert reference["manifestHash"] == canonical_json_hash(manifest)
    from heteroes.noise.selftest import EXPECTED_NOISE_FINGERPRINT
    from heteroes.product.model_qualification import NOISE_FINGERPRINT

    assert NOISE_FINGERPRINT == EXPECTED_NOISE_FINGERPRINT
    assert reference["cell"]["expected"]["perturbedSha256"] != reference["cell"]["negativeExpected"]["perturbedSha256"]
    actual = qualify(root, manifest, reference, device="cpu")
    assert actual == observations
    assert not list(root.glob("*.bin"))


@pytest.mark.parametrize("drift", ["manifest", "scorer-code", "rows", "recipe", "plan", "restore", "seed", "profile"])
def test_reference_inputs_are_checked_before_any_model_is_loaded(new_model, drift, monkeypatch):
    import heteroes.product.model_qualification as probe

    root, manifest = new_model
    reference, _ = build_reference(root, manifest, device="cpu")
    reference = copy.deepcopy(reference)
    if drift == "manifest":
        reference["manifestHash"] = "f" * 64
    elif drift == "scorer-code":
        reference["cell"]["config"]["scorer"] = {"kind": "python", "path": "/must-never-run.py"}
    elif drift == "rows":
        reference["rows"][0]["prompt"] = "different prompt"
    elif drift == "recipe":
        reference["cell"]["recipe"]["evaluation"]["maxNewTokens"] += 1
    elif drift == "plan":
        reference["cell"]["plan"]["population"] += 2
    elif drift == "restore":
        reference["cell"]["negativeExpected"]["restoredSha256"] = "f" * 64
    elif drift == "seed":
        reference["seed"] += 1
    else:
        reference["profile"] = "unrecognized"

    def refuse(*args, **kwargs):
        raise AssertionError("invalid reference must fail before loading")

    monkeypatch.setattr(probe, "observe", refuse)
    with pytest.raises(ValueError):
        qualify(root, manifest, reference, device="cpu")


def test_lab_checks_every_signed_repeat_and_json_identity(new_model):
    from heteroes.product.model_qualification import verify_observations

    root, manifest = new_model
    reference, observations = build_reference(root, manifest, device="cpu")
    assert verify_observations(reference, observations)["passed"]
    for sign in ("1", "-1"):
        for key in observations[sign][0]:
            wrong = copy.deepcopy(observations)
            wrong[sign][0][key] = "drift"
            wrong[sign][1][key] = "drift"
            with pytest.raises(ValueError):
                verify_observations(reference, wrong)
        wrong = copy.deepcopy(observations)
        wrong[sign].pop()
        with pytest.raises(ValueError):
            verify_observations(reference, wrong)
    with pytest.raises(ValueError):
        verify_observations(reference, {"1": observations["1"], "-1": observations["-1"], "extra": []})


def test_reference_validation_imports_no_numerical_libraries_on_the_cpu_lab():
    script = """
import importlib.abc, sys
class NoML(importlib.abc.MetaPathFinder):
    def find_spec(self, name, *args):
        if name.split('.')[0] in ('numpy', 'torch', 'transformers', 'peft'):
            raise AssertionError('CPU lab imported ' + name)
sys.meta_path.insert(0, NoML())
from heteroes.product.model_qualification import check_reference, verify_observations
assert 'torch' not in sys.modules and 'numpy' not in sys.modules
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
