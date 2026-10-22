"""Reference-bound Recipe v3 desktop qualification.

A reference holds two cells, a full-parameter recipe and a LoRA recipe, each with the texts, reward and weight hashes of
one positive and one negative candidate. A device qualifies when it reproduces both cells twice, restores exactly, and
loads the reference's pinned adapter file. Workers never make an adapter from a seed: PyTorch's CPU `uniform_` gives
other bytes for the same seed on native Windows (evidence/2026-10-19-v3-lora-cross-os), so the adapter ships as a file.

The reference is made once (`build_reference`, on the machine whose GPU results were compared across devices) and shipped
beside the desktop runtime; a reference made from a test model only proves the mechanism.
"""

import hashlib
import importlib.metadata
import json
from pathlib import Path
import shutil
import sys
import tempfile

from heteroes.canonical import canonical_json_hash

PROFILE = "desktop-v3"
PEFT_VERSION = "0.21.2"
SEED = 2026101900000003
REFERENCE_FILE = "reference-v3.json"
ADAPTER_FILE = "reference-v3-adapter.bin"
ADAPTER_SPACE = {"kind": "lora", "rank": 4, "alpha": 8, "targetModules": ["q_proj", "v_proj"]}


def reference_rows():
    pairs = [(17 + 7 * i, 23 + 11 * i) for i in range(20)]
    return [{"prompt": f"Compute {a} * {b}. Reply with only the integer.", "answer": a * b} for a, b in pairs]


def cell_configs(model_id, revision, engine=None):
    """The SDK configurations of the two cells, without local paths."""
    common = {
        "model": {"id": model_id, "revision": revision},
        "data": {"batchSize": 4, "batchSeed": 11, "splitSeed": 42},
        "antithetic": True,
        "systemPrompt": None,
        "maxNewTokens": 32,
        "evalDtype": "float32",
        "decoder": "hf_generate",
        "noiseEngine": "cpu",
        **({"noiseEngineVersion": engine} if engine is not None else {}),
        "population": 2,
        "generations": 1,
        "alpha": 0.001,
        "coefficientRule": "zscore@1",
        "scorer": {"kind": "declarative", "name": "last-integer", "config": {}},
    }
    return {
        "full": {**common, "weightSpace": {"kind": "full"}, "sigma": {"kind": "constant", "initial": 0.001}},
        # B starts at zero: a larger sigma is needed for the adapters to change the texts at all
        "lora": {**common, "weightSpace": dict(ADAPTER_SPACE), "sigma": {"kind": "constant", "initial": 0.02}},
    }


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


def _file_sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def observe(model_path, config, rows, seed, device, emit=lambda event: None, adapter=None, expected=None):
    """Run the positive and negative candidate of one cell twice each. With `expected` (a reference cell), the documents
    built on this device must be the reference's before anything is evaluated."""
    import heteroes.executor as execution
    from heteroes.eval.candidate import model_weights_sha256
    from heteroes.manifest import CandidateDescriptor
    from heteroes.model.loading import check_recipe_selftest
    from heteroes.v3.local import prepare
    from heteroes.v3.scoring import score

    with tempfile.TemporaryDirectory(prefix="heteroes-v3-qualification-") as temporary:
        root = Path(temporary)
        rows_file = root / "rows.json"
        rows_file.write_text(json.dumps(rows), encoding="utf-8")
        config = json.loads(json.dumps(config))
        if expected is not None:
            config["noiseEngineVersion"] = expected["recipe"]["noise"]["engine"]
        config["model"]["path"], config["data"]["path"] = str(model_path), str(rows_file)
        ready = prepare(config, root / "run", device, initial_adapter=adapter)
        run = ready["run"]
        if expected is not None and (run.recipe != expected["recipe"] or run.plan != expected["plan"]):
            raise ValueError("V3 model/data/recipe/plan differs from the reference")
        check_recipe_selftest(run, device)
        manifest = {
            "formatVersion": 1,
            "modelId": run.recipe["model"]["id"],
            "revision": run.recipe["model"]["revision"],
            "tokenizerRevision": run.recipe["model"]["tokenizerRevision"],
            "format": "safetensors",
            "files": run.recipe["model"]["files"],
        }
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
        batch = run.batch(ready["dataset"], 0)["rows"]
        observations = {1: [], -1: []}
        original = execution.evaluate_task
        try:
            for index, sign in enumerate((1, -1)):
                descriptor = CandidateDescriptor(
                    run.hash, executor.parent_sha256, "desktop-v3-qualification", 0, index, seed, sign
                )
                for repeat in range(2):
                    space = run.recipe["weightSpace"]["kind"]
                    emit(
                        {"stage": "recipe_v3", "weightSpace": space, "sign": sign, "iteration": repeat + 1, "total": 2}
                    )
                    captured = {}

                    def evaluate(*args, **kwargs):
                        captured["perturbedSha256"] = model_weights_sha256(ready["model"], ready["schema"])
                        return original(*args, **kwargs)

                    execution.evaluate_task = evaluate
                    texts = executor(descriptor)
                    reward, _ = score(run.plan["scorer"], texts, batch)
                    observations[sign].append(
                        {
                            "recipeHash": run.hash,
                            "modelManifestHash": canonical_json_hash(manifest),
                            "parentSha256": executor.parent_sha256,
                            "restoredSha256": model_weights_sha256(ready["model"], ready["schema"]),
                            "outputsHash": canonical_json_hash(texts),
                            "reward": reward,
                            **captured,
                        }
                    )
        finally:
            execution.evaluate_task = original
        return run, observations


def build_reference(model_path, model_id, revision, adapter, device="cuda", emit=lambda event: None, *, engine=None):
    """Observe both cells on this machine and keep what it produced as the reference (repeats must agree)."""
    from heteroes.runtime_info import environment_info

    rows, cells = reference_rows(), {}
    from heteroes.noise.contracts import ENGINE_VERSION

    for name, config in cell_configs(model_id, revision, engine).items():
        run, observations = observe(
            model_path,
            {**config, "noiseEngineVersion": engine or ENGINE_VERSION},
            rows,
            SEED,
            device,
            emit,
            adapter=adapter if name == "lora" else None,
        )
        cell = {"config": config, "recipe": run.recipe, "plan": run.plan}
        cell |= {"expected": observations[1][0], "negativeExpected": observations[-1][0]}
        verify(cell, observations)
        cells[name] = cell
    return {
        "formatVersion": 3,
        "profile": PROFILE,
        "seed": SEED,
        "rows": rows,
        "adapter": {"file": ADAPTER_FILE, "sha256": _file_sha256(adapter)},
        "cells": cells,
        "peftVersion": PEFT_VERSION,
        "environment": environment_info(device),
    }


def write_reference(reference, adapter, directory):
    """Write the reference and its adapter file side by side into a new directory."""
    directory = Path(directory)
    directory.mkdir(parents=True)
    shutil.copyfile(adapter, directory / reference["adapter"]["file"])
    if _file_sha256(directory / reference["adapter"]["file"]) != reference["adapter"]["sha256"]:
        raise ValueError("Reference adapter copy differs")
    (directory / REFERENCE_FILE).write_text(json.dumps(reference, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return directory / REFERENCE_FILE


def update_seconds_per_seed(model_path, recipe, device, seeds=(1, 2)):
    """This machine's coordinator update time per seed on the full model (the lab shows seconds per generation)."""
    import time

    import torch

    from heteroes.es.update import apply_coefficients_
    from heteroes.v3.model import load, trainable_schema

    model, _ = load(model_path, recipe["model"]["files"], device)
    schema = trainable_schema(model, {"kind": "full"})
    if device == "cuda":
        torch.cuda.synchronize()
    started = time.perf_counter()
    apply_coefficients_(
        model,
        schema,
        list(seeds),
        [1.0, -1.0],
        1e-3,
        recipe["noise"]["chunkElements"],
        engine=recipe["noise"]["engine"],
    )
    if device == "cuda":
        torch.cuda.synchronize()
    return round((time.perf_counter() - started) / len(seeds), 3)


def qualify(model_path, reference, reference_dir, device="cuda", emit=lambda event: None):
    from heteroes.model.loading import check_noise_selftest
    from heteroes.product.recovery import source_identity
    from heteroes.product.remote import handle
    from heteroes.runtime_info import environment_info

    if reference.get("formatVersion") != 3 or reference.get("profile") != PROFILE:
        raise ValueError("Desktop v3 needs a desktop-v3 reference")
    if importlib.metadata.version("peft") != PEFT_VERSION:
        raise ValueError("Desktop v3 requires the pinned PEFT version")
    if device == "cuda":
        import torch

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA_UNAVAILABLE")
    adapter = Path(reference_dir) / Path(reference["adapter"]["file"]).name
    if _file_sha256(adapter) != reference["adapter"]["sha256"]:
        raise ValueError("Pinned reference adapter file differs")
    check_noise_selftest()
    from heteroes.model.loading import checked_cpu_noise_engines

    supported_noise_engines = checked_cpu_noise_engines()
    evidence = {}
    for name in ("full", "lora"):
        cell = reference["cells"][name]
        if cell["config"]["scorer"].get("kind") != "declarative":
            raise ValueError("Desktop v3 needs a declarative v3 reference")
        _, observations = observe(
            model_path,
            cell["config"],
            reference["rows"],
            reference["seed"],
            device,
            emit,
            adapter=adapter if name == "lora" else None,
            expected=cell,
        )
        evidence[name] = verify(cell, observations)
    gpu = handle({"action": "probe"}) if device == "cuda" else {"gpuName": "CPU reference", "vramTotalMb": 1}
    emit({"stage": "update_speed"})
    return {
        "passed": True,
        # any machine may coordinate (owner 2026-10-20): the update has the same bits everywhere; its speed is reported
        "coordinator": True,
        "updateSecondsPerSeed": update_seconds_per_seed(model_path, reference["cells"]["full"]["recipe"], device),
        "gpuName": gpu["gpuName"],
        "vramTotalMb": gpu["vramTotalMb"],
        **({"gpuUUID": gpu["gpuUUID"]} if "gpuUUID" in gpu else {}),
        **({"gpuIndex": gpu["gpuIndex"]} if "gpuIndex" in gpu else {}),
        "noiseVersion": reference["cells"]["full"]["recipe"]["noise"]["engine"],
        "supportedNoiseEngines": supported_noise_engines,
        "platform": "windows" if sys.platform == "win32" else "linux",
        "runtimeProfile": PROFILE,
        "recipeVersions": [3],
        "qualifiedModelHashes": [evidence["full"]["modelManifestHash"]],
        "compatibility": {
            "passed": True,
            "repeatIdentical": True,
            "recipeV3": evidence["full"],
            "recipeV3Lora": evidence["lora"],
            "peftVersion": PEFT_VERSION,
            "initialAdapterSha256": reference["adapter"]["sha256"],
        },
        "environment": {**environment_info(device), **source_identity(Path(__file__).resolve().parents[1])},
    }
