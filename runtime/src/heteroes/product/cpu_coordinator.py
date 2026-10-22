"""CPU-only v3 coordination: admit update arithmetic without qualifying generated texts.

Constants can be imported by the CPU lab without importing numerical libraries. The known answer comes from the
independent NumPy oracle in docs/evidence/2026-10-20-cpu-coordinator; it exercises a non-power-of-two population.
"""

PROFILE = "coordinator-cpu-v3"
UPDATE_EVIDENCE = {
    "version": 1,
    "schemaHash": "dccf3b4a32c06af71831a5645b07beeedfddf1c61bd9be267f603b740b76dbba",
    "parentSha256": "d1254dcd275cbbd842bfd1b91c3597e3ccef79712811221e03a007c15ca3d9e2",
    "updatedSha256": "0646ab4cabef88213c7803683b4951e240b1da6687b7d33c7eb42b7859504b10",
}
UPDATE_EVIDENCE_V2 = {
    **UPDATE_EVIDENCE,
    "updatedSha256": "ddcb2770a92a7dd24f9f02625a8687cc9c69f8a74896ee74351c2d70f76204b5",
}


def coordinator_only(profile):
    return profile.get("runtimeProfile") == PROFILE


def check_update(engine=None):
    import hashlib

    import numpy as np
    import torch

    from heteroes.es.update import apply_coefficients_
    from heteroes.model.loading import check_noise_selftest
    from heteroes.model.schema import build_parameter_schema
    from heteroes.noise.contracts import ENGINE_VERSION, ENGINE_V2

    engine = ENGINE_VERSION if engine is None else engine
    check_noise_selftest(engine)
    expected = UPDATE_EVIDENCE_V2 if engine == ENGINE_V2 else UPDATE_EVIDENCE
    baseline = ((np.arange(200_003, dtype=np.int32) % 251 - 125) / 4096).astype(np.float16)
    observed = []
    for _ in range(2):
        model = torch.nn.Module()
        model.register_parameter("w", torch.nn.Parameter(torch.from_numpy(baseline.copy())))
        schema = build_parameter_schema(model)
        parent = hashlib.sha256(model.w.detach().numpy().tobytes()).hexdigest()
        apply_coefficients_(model, schema, [5, 6, 7], [1.0, -0.5, 0.25], 0.05, 65536, engine=engine)
        observed.append(
            {
                "version": 1,
                "schemaHash": schema.hash,
                "parentSha256": parent,
                "updatedSha256": hashlib.sha256(model.w.detach().numpy().tobytes()).hexdigest(),
            }
        )
    if any(value != expected for value in observed):
        raise ValueError("CPU coordinator update known-answer mismatch")
    return dict(expected)


def qualify(emit=lambda event: None):
    import sys
    from pathlib import Path

    from heteroes.product.recovery import source_identity
    from heteroes.runtime_info import environment_info

    emit({"stage": "update_known_answer"})
    evidence = check_update()
    from heteroes.model.loading import checked_cpu_noise_engines
    from heteroes.noise.contracts import ENGINE_V2

    v2_evidence = check_update(ENGINE_V2)
    return {
        "passed": True,
        "coordinator": True,
        "gpuName": "CPU coordinator",
        "vramTotalMb": 0,
        "noiseVersion": "numpy_pcg64_normal_f32_to_f16_v1",
        "supportedNoiseEngines": checked_cpu_noise_engines(),
        "platform": "windows" if sys.platform == "win32" else "linux",
        "runtimeProfile": PROFILE,
        "recipeVersions": [3],
        "qualifiedModelHashes": [],
        "compatibility": {"updateKnownAnswer": evidence, "updateKnownAnswerV2": v2_evidence},
        "updateSecondsPerSeed": None,
        "environment": {**environment_info("cpu"), **source_identity(Path(__file__).resolve().parents[1])},
    }
