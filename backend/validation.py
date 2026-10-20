from .policies import backup_policy as validated_backup_policy, v2_qualification, v3_qualification

from fastapi import HTTPException
from .constants import V3_CODE_KEYS, V3_KEYS, V3_UPDATE_KEYS
from heteroes.catalog import DECODE_ENGINES


def freeze_python_code(body):
    """
    Pin uploaded researcher code (owner 2026-10-20: Python rewards are open on the web lab). Each file gets its SHA-256,
    which also completes a Python scorer spec and a `python@1` coefficient rule; validate_options then checks that the plan
    pins exactly these files. The code runs only on the coordinator device, in a child process with a time limit.
    """
    from heteroes.v3.scoring import source_sha256

    entries = body.get("pythonCode") or []
    if not entries:
        body.pop("pythonCode", None)
        return
    frozen = []
    for entry in entries:
        if set(entry) - {"codeSha256"} != {"role", "name", "function", "source"} or not isinstance(
            entry["source"], str
        ):
            raise ValueError("A Python code file has a role, name, function and source")
        frozen.append({**entry, "codeSha256": source_sha256(str(entry["name"]), entry["source"].encode())})
    for entry in frozen:
        if entry["role"] == "scorer" and body["scorer"].get("kind") == "python":
            body["scorer"] = {**body["scorer"], "codeSha256": entry["codeSha256"]}
        if entry["role"] == "coefficients" and body["coefficientRule"].startswith("python@1"):  # also a re-upload
            body["coefficientRule"] = "python@1:" + entry["codeSha256"]
    body["pythonCode"] = frozen


def validate_configuration(config, current, *, store, runtime, registry, scoped, capabilities):
    current = scoped(current, current["workspaceId"])
    cap = capabilities()
    body = config.model_dump()
    if body.get("candidateSeedNamespace") is None:
        body.pop("candidateSeedNamespace", None)
    co = next((d for d in runtime.devices() if d["deviceId"] == body["coordinatorDeviceId"]), None)
    if (
        not co
        or co["approvalStatus"] != "APPROVED"
        or co["workspaceId"] != current["workspaceId"]
        or not co["selfTest"]["coordinator"]
    ):
        raise HTTPException(422, "Select an approved coordinator in this workspace")
    try:
        body["backupPolicy"] = validated_backup_policy(body.get("backupPolicy") or {"interval": 1, "retain": 3})
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    if body["recipeVersion"] in (2, 3):
        model = registry.get(body["modelArtifactId"], current["workspaceId"], "model")
        if model["status"] not in ("READY", "REGISTERED") or model["reference"] != body["modelName"]:
            raise HTTPException(422, "Model is unavailable or its name differs")
        if len(body["datasetIds"]) != 1:
            raise HTTPException(422, "Select one frozen dataset")
        data = registry.get(body["datasetIds"][0], current["workspaceId"], "dataset")
        if (
            body["batchSize"] > data["counts"]["train"]
            or body["sigmaSchedule"] not in ("constant", "cosine")
            or body["sigmaMinimum"] > body["sigma"]
        ):
            raise HTTPException(422, "Invalid batch size or sigma schedule")
        version = body["recipeVersion"]
        if version == 2:
            from heteroes.study.models import validate as validate_model

            try:
                validate_model(model["manifest"])
            except ValueError as error:
                raise HTTPException(422, str(error)) from None
        if data.get("recipeVersion", 2) != version:
            raise HTTPException(422, "Dataset format differs from the selected recipe")
        if version == 3:
            from heteroes.v3.options import validate_options

            try:
                freeze_python_code(body)
                validate_options(body, allow_python=True)
                config = body["scorer"]["config"]
                fields = [config[k] for k in sorted(config) if k.endswith("Field")] or ["answer"]
                # a Python scorer reads the rows itself; a declarative one names its columns
                if body["scorer"]["kind"] == "declarative" and not set(fields) <= set(data.get("columns", [])):
                    raise ValueError("Scorer fields must exist in every dataset row")
            except (ValueError, TypeError, KeyError) as error:
                raise HTTPException(422, str(error)) from None
        # Recipe v3 may choose the compacting decoder (validate_options above); Recipe v2 keeps generate()
        if body["task"] != ("text_v3" if version == 3 else "text_math_v2") or (
            version == 2 and body["decodeEngine"] != "hf_generate"
        ):
            raise HTTPException(422, "Recipe v2 uses exact math and the HF decoder")
        selected = [
            d
            for d in runtime.devices()
            if d["deviceId"] == body["coordinatorDeviceId"] or d["workerId"] in body["workerIds"]
        ]
        for d in selected:
            profile = d["selfTest"]
            qualification = (v3_qualification if version == 3 else v2_qualification)(profile, model["manifestHash"])
            if qualification == "recipe":
                raise HTTPException(
                    422, f"Selected device requires Recipe v{version} qualification; Windows remains v1 worker-only"
                )
            if qualification == "model":
                raise HTTPException(422, "Qualify every selected device for this pinned model")
        body.update(
            modelManifest=model["manifest"],
            modelSource=model["source"],
            datasetObjectSha256=data["objectSha256"],
            datasetIdentity=data["identity"],
        )
        if data.get("splitObjects"):  # a file-backed dataset: its split files may be transferred too
            body["datasetSplitObjects"] = data["splitObjects"]
    else:
        if body["modelName"] != cap["modelId"] or body["modelArtifactId"] != "qwen-pinned":
            raise HTTPException(422, "Only the pinned Qwen model is supported for Recipe v1")
        if body["task"] not in cap["workloads"] or body["decodeEngine"] not in DECODE_ENGINES or body["datasetIds"]:
            raise HTTPException(422, "Select a built-in workload and decoder for Recipe v1")
        for key in (
            "recipeVersion",
            "batchSize",
            "batchSeed",
            "sigmaSchedule",
            "sigmaMinimum",
            "maxNewTokens",
            "validationInterval",
        ):
            body.pop(key)
    if body.get("recipeVersion") != 3:
        for key in (*V3_KEYS, *V3_UPDATE_KEYS, *V3_CODE_KEYS):
            body.pop(key, None)
    if body["schedulerPolicy"] not in cap["schedulerPolicies"] or body["syncMode"] not in cap["syncModes"]:
        raise HTTPException(422, "Unsupported scheduling policy or synchronization mode")
    if len(set(body["workerIds"])) != len(body["workerIds"]) or not set(body["workerIds"]) <= set(cap["workerIds"]):
        raise HTTPException(422, "Select configured workers without duplicates")
    if set(body["workerIds"]) & set(cap.get("quarantinedWorkerIds", [])):
        raise HTTPException(422, "Selected worker is quarantined after a restore mismatch")
    store.ensure_workers(cap["workerIds"])
    if not set(body["workerIds"]) <= set(store.assignments(current["workspaceId"])):
        raise HTTPException(422, "Select GPUs assigned to this workspace")
    return body
