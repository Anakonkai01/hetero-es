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


def test_model_references_pin_the_engine_and_preserve_legacy_config(new_model):
    from heteroes.noise.contracts import ENGINE_VERSION, ENGINE_V2

    root, manifest = new_model
    old, _ = build_reference(root, manifest, device="cpu")
    assert old["cell"]["recipe"]["noise"]["engine"] == ENGINE_VERSION
    assert "noiseEngineVersion" not in old["cell"]["config"]
    new, observations = build_reference(root, manifest, device="cpu", engine=ENGINE_V2)
    assert new["cell"]["recipe"]["noise"]["engine"] == ENGINE_V2
    assert new["cell"]["config"]["noiseEngineVersion"] == ENGINE_V2
    assert new["cell"]["expected"]["perturbedSha256"] != old["cell"]["expected"]["perturbedSha256"]
    assert check_reference(new, manifest) is new
    assert qualify(root, manifest, new, device="cpu") == observations
    bad = copy.deepcopy(new)
    bad["cell"]["recipe"]["noise"] = old["cell"]["recipe"]["noise"]
    with pytest.raises(ValueError):
        check_reference(bad, manifest)


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


# ---- M4: a strict_b22_v1 qualification is a separate reference, keyed by its decoder ------------------------------

gpu = pytest.mark.skipif(
    __import__("os").environ.get("HETEROES_GPU_ACCEPTANCE") != "1", reason="strict qualification runs on an NVIDIA GPU"
)


def test_strict_documents_and_configs_differ_only_in_the_decoder_identity():
    from heteroes.catalog import STRICT_B22_DECODER
    from heteroes.product.model_qualification import _documents, qualification_key
    from heteroes.product.qualification_v3 import cell_configs
    from heteroes.noise.contracts import ENGINE_V2

    plain, strict = cell_configs("m", "r" * 40)["full"], cell_configs("m", "r" * 40, decoder=STRICT_B22_DECODER)["full"]
    assert {k for k in strict if strict[k] != plain.get(k)} == {"evalDtype", "decoder"}
    assert strict["evalDtype"] == "float16" and strict["decoder"] == STRICT_B22_DECODER
    assert cell_configs("m", "r" * 40, decoder="hf_generate") == cell_configs("m", "r" * 40)  # old bytes kept
    manifest = {"modelId": "m", "revision": "r" * 40, "tokenizerRevision": "r" * 40, "files": {}}
    recipe, _ = _documents(manifest, "a" * 64, "b" * 64, decoder=STRICT_B22_DECODER)
    assert recipe["evaluation"]["decoder"] == STRICT_B22_DECODER and recipe["evaluation"]["evalDtype"] == "float16"
    with pytest.raises(ValueError):
        _documents(manifest, "a" * 64, "b" * 64, decoder="hf_compact")
    # the lab keys qualifications by noise engine, and by decoder for the strict identity only
    assert qualification_key(ENGINE_V2) == ENGINE_V2 == qualification_key(ENGINE_V2, "hf_generate")
    assert qualification_key(ENGINE_V2, STRICT_B22_DECODER) == f"{ENGINE_V2}+{STRICT_B22_DECODER}"
    with pytest.raises(ValueError):
        qualification_key(ENGINE_V2, "hf_compact")


@gpu
def test_a_strict_reference_round_trips_on_the_gpu_and_cannot_pass_as_a_plain_one(new_model):
    from heteroes.catalog import STRICT_B22_DECODER
    from heteroes.noise.contracts import ENGINE_V2

    root, manifest = new_model
    plain, _ = build_reference(root, manifest, device="cpu", engine=ENGINE_V2)
    strict, observations = build_reference(root, manifest, device="cuda", engine=ENGINE_V2, decoder=STRICT_B22_DECODER)
    assert strict["cell"]["recipe"]["evaluation"]["decoder"] == STRICT_B22_DECODER
    assert check_reference(strict, manifest) is strict
    assert qualify(root, manifest, strict, device="cuda") == observations
    mixed = copy.deepcopy(strict)
    mixed["cell"]["config"] = plain["cell"]["config"]  # a strict recipe under the plain probe config
    with pytest.raises(ValueError):
        check_reference(mixed, manifest)
