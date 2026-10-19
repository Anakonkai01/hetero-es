"""Staged reference-bound v3 desktop qualification.

WIP: not wired into the desktop entry point. Reference generation, packaged
admission and native Windows canonical-adapter handling remain to be completed.
Only the pure reference-verification helper has been unit-tested so far.
"""

import importlib.metadata
import json
from pathlib import Path
import sys
import tempfile

from heteroes.canonical import canonical_json_hash


def verify(reference, observations):
    for sign, key in ((1, "expected"), (-1, "negativeExpected")):
        repeated = observations[sign]
        if len(repeated) != 2 or repeated[0] != repeated[1]:
            raise ValueError("Repeated signed candidate differs")
        expected, actual = reference[key], repeated[0]
        if actual.get("parentSha256") != actual.get("restoredSha256"):
            raise ValueError("Candidate exact restore mismatch")
        if actual != expected:
            raise ValueError("V3 candidate differs from the qualified reference")
    return {
        "passed": True,
        "repeatIdentical": True,
        **observations[1][0],
        "negativeProbeHash": canonical_json_hash(observations[-1][0]),
    }


def observe(model_path, reference, device="cuda", emit=lambda event: None):
    import heteroes.executor as execution
    from heteroes.eval.candidate import model_weights_sha256
    from heteroes.manifest import CandidateDescriptor
    from heteroes.model.loading import check_noise_selftest, check_recipe_selftest
    from heteroes.v3.local import prepare
    from heteroes.v3.scoring import score

    if reference.get("formatVersion") != 3 or reference["config"]["scorer"].get("kind") != "declarative":
        raise ValueError("Desktop v3 needs a declarative v3 reference")
    check_noise_selftest()
    with tempfile.TemporaryDirectory(prefix="heteroes-v3-qualification-") as temporary:
        root = Path(temporary)
        rows = root / "rows.json"
        rows.write_text(json.dumps(reference["rows"]), encoding="utf-8")
        config = json.loads(json.dumps(reference["config"]))
        config["model"]["path"], config["data"]["path"] = str(model_path), str(rows)
        ready = prepare(config, root / "run", device)
        run = ready["run"]
        if run.recipe != reference["recipe"] or run.plan != reference["plan"]:
            raise ValueError("V3 model/data/recipe/plan differs from the reference")
        check_recipe_selftest(run, device)
        manifest = {
            "formatVersion": 1,
            "modelId": run.recipe["model"]["id"],
            "revision": run.recipe["model"]["revision"],
            "tokenizerRevision": run.recipe["model"]["revision"],
            "format": "safetensors",
            "files": run.recipe["model"]["files"],
        }
        manifest_hash = canonical_json_hash(manifest)
        executor = execution.CandidateExecutor(
            ready["model"],
            ready["tokenizer"],
            ready["schema"],
            run,
            chunk=4,
            dataset=ready["dataset"],
            return_completions=True,
        )
        executor.set_generation(0, run.context(ready["dataset"], 0))
        observations = {1: [], -1: []}
        original = execution.evaluate_task
        try:
            for sign in (1, -1):
                descriptor = CandidateDescriptor(
                    run.hash,
                    executor.parent_sha256,
                    "desktop-v3-qualification",
                    0,
                    0 if sign == 1 else 1,
                    reference["seed"],
                    sign,
                )
                for repeat in range(2):
                    emit({"stage": "recipe_v3", "sign": sign, "iteration": repeat + 1, "total": 2})
                    captured = {}

                    def evaluate(*args, **kwargs):
                        captured["perturbedSha256"] = model_weights_sha256(ready["model"], ready["schema"])
                        return original(*args, **kwargs)

                    execution.evaluate_task = evaluate
                    texts = executor(descriptor)
                    reward, _ = score(run.plan["scorer"], texts, run.batch(ready["dataset"], 0)["rows"])
                    observations[sign].append(
                        {
                            "recipeHash": run.hash,
                            "modelManifestHash": manifest_hash,
                            "parentSha256": executor.parent_sha256,
                            "restoredSha256": model_weights_sha256(ready["model"], ready["schema"]),
                            "outputsHash": canonical_json_hash(texts),
                            "reward": reward,
                            **captured,
                        }
                    )
        finally:
            execution.evaluate_task = original
        # The full model is exactly restored before its optional adapter is initialized.
        del executor
        from heteroes.model.lora import create_initial_adapter

        adapter = create_initial_adapter(
            ready["model"], reference["loraSpace"], reference["loraSeed"], root / "initial-adapter.bin"
        )
        if adapter != reference["initialAdapterSha256"]:
            raise ValueError("PEFT initial adapter differs from the qualified reference")
        return observations


def qualify(model_path, reference, device="cuda", emit=lambda event: None):
    from heteroes.runtime_info import environment_info
    from heteroes.product.recovery import source_identity
    from heteroes.product.remote import handle

    if importlib.metadata.version("peft") != "0.21.2":
        raise ValueError("Desktop v3 requires the pinned PEFT version")
    evidence = verify(reference, observe(model_path, reference, device, emit))
    gpu = handle({"action": "probe"}) if device == "cuda" else {"gpuName": "CPU reference", "vramTotalMb": 1}
    return {
        "passed": True,
        "coordinator": sys.platform != "win32" and gpu["vramTotalMb"] >= 11000,
        "gpuName": gpu["gpuName"],
        "vramTotalMb": gpu["vramTotalMb"],
        **({"gpuUUID": gpu["gpuUUID"]} if "gpuUUID" in gpu else {}),
        "noiseVersion": reference["recipe"]["noise"]["engine"],
        "platform": "windows" if sys.platform == "win32" else "linux",
        "runtimeProfile": "desktop-v3",
        "recipeVersions": [3],
        "qualifiedModelHashes": [evidence["modelManifestHash"]],
        "compatibility": {
            "passed": True,
            "repeatIdentical": True,
            "recipeV3": evidence,
            "peftVersion": "0.21.2",
            "initialAdapterSha256": reference["initialAdapterSha256"],
        },
        "environment": {**environment_info(device), **source_identity(Path(__file__).resolve().parents[1])},
    }
