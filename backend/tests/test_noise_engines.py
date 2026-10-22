"""Engine capabilities must gate coordination and elastic admission."""

import pytest
from pydantic import ValidationError

from backend.device_models import SelfTest
from backend.policies import noise_qualification
from heteroes.noise.contracts import ENGINE_VERSION, ENGINE_V2, EXPECTED_V2_NOISE_FINGERPRINT


def test_legacy_profile_only_admits_v1():
    assert noise_qualification({}, ENGINE_VERSION) is None
    assert noise_qualification({}, ENGINE_V2) == "noise"


def test_engine_fingerprint_required_and_unknown_engine_rejected():
    profile = {"supportedNoiseEngines": {ENGINE_V2: EXPECTED_V2_NOISE_FINGERPRINT}}
    assert noise_qualification(profile, ENGINE_V2) is None
    assert noise_qualification(profile, ENGINE_VERSION) == "noise"
    assert noise_qualification(profile, "unknown") == "noise"
    profile["supportedNoiseEngines"][ENGINE_V2] = "0" * 64
    assert noise_qualification(profile, ENGINE_V2) == "noise"


def test_selftest_rejects_unknown_or_wrong_engine_fingerprint():
    base = dict(passed=True, gpuName="test", vramTotalMb=1, noiseVersion=ENGINE_VERSION)
    for engines in ({"unknown": "a" * 64}, {ENGINE_V2: "a" * 64}):
        with pytest.raises(ValidationError):
            SelfTest(**base, supportedNoiseEngines=engines)
    parsed = SelfTest(**base, supportedNoiseEngines={ENGINE_V2: EXPECTED_V2_NOISE_FINGERPRINT})
    assert parsed.supportedNoiseEngines[ENGINE_V2] == EXPECTED_V2_NOISE_FINGERPRINT


def test_model_qualification_is_bound_to_its_noise_engine():
    from backend.policies import v3_qualification

    model = "d" * 64
    old = {"recipeVersions": [3], "noiseVersion": ENGINE_VERSION, "qualifiedModelHashes": [model]}
    assert v3_qualification(old, model, ENGINE_VERSION) is None
    assert v3_qualification(old, model, ENGINE_V2) == "model"
    both = {**old, "qualifiedModelsByNoiseEngine": {ENGINE_VERSION: [model], ENGINE_V2: [model]}}
    assert v3_qualification(both, model, ENGINE_V2) is None
    assert v3_qualification(both, "e" * 64, ENGINE_V2) == "model"


def test_native_windows_v2_requires_the_matching_full_and_lora_reference():
    import json
    from pathlib import Path

    receipt = Path(__file__).parents[2] / "docs/evidence/2026-10-22-candidate14/gpu-v2-windows-source-first.json"
    body = json.loads(receipt.read_text())
    for key in ("qualificationSeconds", "modelPipelineMeasurements"):
        body.pop(key)
    assert SelfTest(**body).noiseVersion == ENGINE_V2
    with pytest.raises(ValidationError):
        SelfTest(**{**body, "qualifiedModelsByNoiseEngine": {ENGINE_VERSION: ["f" * 64]}})
    body["noiseVersion"] = ENGINE_VERSION
    with pytest.raises(ValidationError):
        SelfTest(**body)
