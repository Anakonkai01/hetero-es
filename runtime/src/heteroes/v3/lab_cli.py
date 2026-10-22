"""Offer a CLI specification to a managed lab through its existing assets, device and experiment APIs."""

import json
import os
from pathlib import Path
import threading
import time
import urllib.error
import urllib.request

from heteroes.canonical import canonical_json_hash
from heteroes.http_transport import USER_AGENT
from heteroes.product.files import read_json, write_json
from heteroes.product.worker_cli import sha256_file


class Lab:
    def __init__(self, url, workspace, token_env="HETEROES_LAB_ACCESS_TOKEN"):
        self.url, self.workspace = url.rstrip("/"), workspace
        self.token = os.environ.get(token_env)
        if not self.token:
            raise ValueError(f"Set {token_env} to the lab user access token in the environment")

    def request(self, method, path, body=None):
        data = None if body is None else json.dumps(body, allow_nan=False).encode()
        request = urllib.request.Request(
            self.url + path,
            method=method,
            data=data,
            headers={
                "Authorization": "Bearer " + self.token,
                "X-Workspace-Id": self.workspace,
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT,  # the public lab's edge refuses urllib's default agent (HTTP 403)
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            try:
                detail = json.load(error).get("detail")
            except (ValueError, AttributeError):
                detail = None
            raise RuntimeError(f"Lab HTTP {error.code}: {detail if isinstance(detail, str) else path}") from None

    def upload(self, plan, path):
        # Signed storage capability only: never send the user's bearer credential to an upload URL.
        try:
            with Path(path).open("rb") as stream:
                headers = {"User-Agent": USER_AGENT, **plan["headers"]}
                request = urllib.request.Request(plan["url"], method="PUT", data=stream, headers=headers)
                with urllib.request.urlopen(request, timeout=600) as response:
                    response.read()
        except (urllib.error.URLError, OSError):
            raise RuntimeError("Signed artifact upload failed; private receipt retained for retry") from None


def _code(config, role):
    path = Path(config["path"])
    from heteroes.v3.scoring import source_sha256

    source = path.read_bytes()
    return {
        "role": role,
        "name": path.name,
        "function": config["function"],
        "source": source.decode("utf-8"),
        "codeSha256": source_sha256(path.name, source),
    }


def _managed_choices(spec):
    if spec.get("evalDtype", "float32") != "float32" or spec.get("noiseEngine", "cpu") != "cpu":
        raise ValueError("The managed lab uses FP32 evaluation and canonical CPU noise")


def managed_configuration(spec, coordinator, workers, model, dataset):
    _managed_choices(spec)
    sigma, data = spec["sigma"], spec["data"]
    schedule = spec.get("alphaSchedule") or {"kind": "constant"}
    momentum = spec.get("momentum") or {}
    scorer = spec["scorer"]
    code = []
    if scorer["kind"] == "python":
        entry = _code(scorer, "scorer")
        code.append(entry)
        scorer = {
            "kind": "python",
            "name": scorer["name"],
            "version": scorer.get("version", 1),
            "codeSha256": entry["codeSha256"],
            "config": {},
        }
    else:
        scorer = {
            "kind": "declarative",
            "name": scorer["name"],
            "version": scorer.get("version", 1),
            "codeSha256": None,
            "config": scorer.get("config", {}),
        }
    rule = spec.get("coefficientRule", "zscore@1")
    if isinstance(rule, dict):
        entry = _code(rule, "coefficients")
        code.append(entry)
        rule = "python@1:" + entry["codeSha256"]
    result = {
        "name": spec.get("name", "CLI experiment"),
        "recipeVersion": 3,
        "modelName": spec["model"]["id"],
        "modelArtifactId": model["id"],
        "datasetIds": [dataset["datasetId"]],
        "coordinatorDeviceId": coordinator,
        "workerIds": list(workers),
        "task": "text_v3",
        "maxGenerations": spec["generations"],
        "candidatesPerGeneration": spec["population"],
        "alpha": spec["alpha"],
        "sigma": sigma["initial"],
        "sigmaMinimum": sigma.get("minimum", sigma["initial"]),
        "sigmaSchedule": sigma.get("kind", "constant"),
        "batchSize": data["batchSize"],
        "batchSeed": data.get("batchSeed", 11),
        "sampler": data.get("sampler", spec.get("sampler", "sha256-python-random-sample-v1")),
        "weightSpace": spec.get("weightSpace", {"kind": "full"}),
        "antithetic": spec.get("antithetic", False),
        "maxNewTokens": spec.get("maxNewTokens", 256),
        "systemPrompt": spec.get("systemPrompt"),
        "decodeEngine": spec.get("decoder", "hf_generate"),
        "scorer": scorer,
        "coefficientRule": rule,
        "alphaSchedule": schedule["kind"],
        "alphaMinimum": schedule.get("minimum"),
        "momentumBeta": momentum.get("beta"),
        "momentumWindow": momentum.get("window", 4),
        **({"pythonCode": code} if code else {}),
        **{
            key: spec[key]
            for key in (
                "candidateSeedNamespace",
                "evalChunk",
                "evalChunks",
                "pythonTimeoutSeconds",
                "promptFormat",
                "validationInterval",
                "allowJoin",
                "schedulerPolicy",
            )
            if key in spec
        },
    }
    return result


def offer_experiment(spec, coordinator, workers, api, directory):
    """Upload frozen local inputs and create one draft; receipt identity makes a retry idempotent."""
    from heteroes.v3.model import file_manifest, registration_manifest

    _managed_choices(spec)
    root = Path(directory)
    model_path = Path(spec["model"]["path"])
    files = file_manifest(model_path)
    revision = spec["model"].get("revision") or canonical_json_hash(files)[:40]
    manifest = registration_manifest(model_path, spec["model"]["id"], revision)
    data = spec["data"]
    sources = {name: Path(path) for name, path in data.get("splits", {"all": data.get("path")}).items()}
    identity = {
        "specHash": canonical_json_hash(spec),
        "modelManifestHash": canonical_json_hash(manifest),
        "dataFiles": {name: sha256_file(path) for name, path in sources.items()},
        "code": {
            role: sha256_file(choice["path"])
            for role, choice in (("scorer", spec["scorer"]), ("coefficients", spec.get("coefficientRule")))
            if isinstance(choice, dict) and choice.get("kind") == "python"
        },
        "coordinatorDeviceId": coordinator,
        "workerIds": list(workers),
    }
    state = read_json(root / "lab-offer.json", {"identity": identity})
    if state["identity"] != identity:
        raise ValueError("Local input identity changed; use a fresh output directory")
    write_json(root / "lab-offer.json", state)
    if state.get("experimentId"):
        return api.request("GET", "/api/v1/experiments/" + state["experimentId"])
    models = api.request("GET", "/api/v1/models")
    model = next(
        (
            m
            for m in models
            if (state.get("modelId") is not None and m.get("id") == state["modelId"])
            or (m.get("manifestHash") == identity["modelManifestHash"] and m.get("status") in ("READY", "REGISTERED"))
        ),
        None,
    )
    if model is None:
        model = api.request(
            "POST",
            "/api/v1/models/register",
            {"recipeVersion": 3, "name": "CLI pinned model", "manifest": manifest, "source": "UPLOAD"},
        )
        state["modelId"] = model["id"]
        write_json(root / "lab-offer.json", state)
    if model["status"] == "AWAITING_FILES":
        plans = api.request(
            "POST",
            f"/api/v1/models/{model['id']}/upload-plan",
            {name: (model_path / name).stat().st_size for name in files},
        )
        for name, plan in plans.items():
            api.upload(plan, model_path / name)
        model = api.request("POST", f"/api/v1/models/{model['id']}/publish")
    if state.get("datasetId"):
        dataset = next(d for d in api.request("GET", "/api/v1/datasets") if d["datasetId"] == state["datasetId"])
    else:
        plan = api.request(
            "POST",
            "/api/v1/datasets/upload-plan",
            {
                "name": "CLI dataset",
                "files": {
                    name: {"format": path.suffix.lstrip("."), "sizeBytes": path.stat().st_size}
                    for name, path in sources.items()
                },
            },
        )
        for name, target in plan["files"].items():
            api.upload(target, sources[name])
        dataset = api.request(
            "POST",
            f"/api/v1/datasets/uploads/{plan['uploadId']}/build",
            {"mapping": {"prompt": data.get("promptField", "prompt")}, "splitSeed": data.get("splitSeed", 42)},
        )
        state["datasetId"] = dataset["datasetId"]
        write_json(root / "lab-offer.json", state)
    configuration = managed_configuration(spec, coordinator, workers, model, dataset)
    experiment = api.request("POST", "/api/v1/experiments", configuration)
    state["experimentId"] = experiment["experimentId"]
    write_json(root / "lab-offer.json", state)
    return experiment


def serve_lab(
    spec,
    lab_url,
    directory,
    *,
    workspace,
    host,
    worker_ids,
    worker_home=None,
    device="cpu",
    token_env="HETEROES_LAB_ACCESS_TOKEN",
    approval_timeout=600,
):
    """Use the installed CLI Worker's device agent; approval and boot-scoped contribution stay owner-controlled."""
    from heteroes.product.desktop_bridge import Bridge
    from heteroes.product.worker_cli import Worker, lab_request
    from heteroes.product.cpu_coordinator import coordinator_only
    from heteroes.v3.distributed import _signals

    if not workspace or not host or not worker_ids:
        raise ValueError("--lab needs --workspace, --host and --worker-ids")
    api = Lab(lab_url, workspace, token_env)
    worker = Worker(worker_home)
    settings = worker.settings()
    profile = settings.get("selfTest", {})
    if not worker.installed() or not profile.get("passed") or not profile.get("coordinator"):
        raise ValueError("Install heteroes-worker and pass its coordinator self-test first")
    if (device == "cpu") != coordinator_only(profile):
        raise ValueError("--device must match the installed Worker's self-test profile")
    if settings.get("device"):
        if settings.get("serverUrl", "").rstrip("/") != lab_url.rstrip("/"):
            raise ValueError("This Worker is paired to another lab")
        compute = worker.compute(True, host)
        if settings.get("compute") != compute:
            advertised = {**profile, "coordinator": True}
            api.request(
                "PATCH",
                f"/api/v1/devices/{settings['device']['deviceId']}/configuration",
                {"computeUrl": f"http://{host}:8765", "selfTest": advertised},
            )
            worker.save_settings({**settings, "compute": compute})
    else:
        code = api.request("POST", "/api/v1/devices/pairing-codes")["code"]
        worker.join(lab_url, code, "CLI coordinator", coordinator=True, host=host)
    settings = worker.settings()
    config = worker.agent_config()
    secret = worker.paths()["token"].read_text()
    bridge = Bridge(config, secret)
    stop, handlers = threading.Event(), {}
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        handlers = _signals(stop)
        worker.declare_qualification(bridge, settings, secret, lab_request)
        device_id = settings["device"]["deviceId"]
        print("Coordinator online; waiting for administrator approval in the selected workspace.", flush=True)
        deadline = time.monotonic() + approval_timeout
        while not stop.is_set():
            owned = api.request("GET", "/api/v1/devices")
            current = next(d for d in owned if d["deviceId"] == device_id)
            if current["approvalStatus"] == "APPROVED" and current["workspaceId"] == workspace:
                break
            if current["approvalStatus"] in ("REVOKED", "QUARANTINED") or time.monotonic() >= deadline:
                raise ValueError("Administrator approval in this workspace is required")
            stop.wait(0.5)
        if stop.is_set():
            return 0
        experiment = offer_experiment(spec, device_id, worker_ids, api, root)
        if experiment["status"] in ("COMPLETED", "FAILED", "CANCELLED"):
            return 1 if experiment["status"] == "FAILED" else 0
        if experiment["status"] == "DRAFT":
            api.request("POST", f"/api/v1/experiments/{experiment['experimentId']}/submit")
        print(
            json.dumps(
                {
                    "experimentId": experiment["experimentId"],
                    "deviceId": device_id,
                    "contribution": "Turn ON in the lab for this boot to allow execution",
                }
            ),
            flush=True,
        )
        state_path = worker.paths()["agentState"] / "runs" / experiment["experimentId"] / "state.json"
        while not stop.is_set():
            status = read_json(state_path, {}).get("status")
            if status in ("COMPLETED", "FAILED", "CANCELLED"):
                return 1 if status == "FAILED" else 0
            stop.wait(0.5)
        return 0
    finally:
        while not bridge.call("quit")["drained"]:
            time.sleep(0.5)
        for number, previous in handlers.items():
            import signal

            signal.signal(number, previous)
