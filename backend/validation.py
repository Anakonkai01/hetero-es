from .policies import backup_policy as validated_backup_policy, v2_qualification

from fastapi import HTTPException


def validate_configuration(config, current, *, store, runtime, registry, scoped, capabilities):
    current = scoped(current, current["workspaceId"])
    cap = capabilities()
    body = config.model_dump()
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
    if body["recipeVersion"] == 2:
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
        if body["task"] != "text_math_v2" or body["decodeEngine"] != "hf_generate":
            raise HTTPException(422, "Recipe v2 uses exact math and the HF decoder")
        selected = [
            d
            for d in runtime.devices()
            if d["deviceId"] == body["coordinatorDeviceId"] or d["workerId"] in body["workerIds"]
        ]
        for d in selected:
            profile = d["selfTest"]
            if v2_qualification(profile, model["manifestHash"]) == "recipe":
                raise HTTPException(
                    422, "Selected device requires Recipe v2 qualification; Windows remains v1 worker-only"
                )
            if v2_qualification(profile, model["manifestHash"]) == "model":
                raise HTTPException(422, "Qualify every selected device for this pinned model")
        body.update(
            modelManifest=model["manifest"],
            modelSource=model["source"],
            datasetObjectSha256=data["objectSha256"],
            datasetIdentity=data["identity"],
        )
    else:
        if body["modelName"] != cap["modelId"] or body["modelArtifactId"] != "qwen-pinned":
            raise HTTPException(422, "Only the pinned Qwen model is supported for Recipe v1")
        if (
            body["task"] not in cap["workloads"]
            or body["decodeEngine"] not in ("hf_generate", "hf_compact")
            or body["datasetIds"]
        ):
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
