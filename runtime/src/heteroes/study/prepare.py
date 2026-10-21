"""Prepare immutable dataset/model files through private assignment grants."""

import hashlib
import json
import os
from pathlib import Path
import socket
import tempfile
import urllib.request
from urllib.parse import urlsplit
from heteroes.catalog import PINNED_MODEL_ID, PINNED_REVISION
from .data import verify as verify_data, sha
from .models import verify as verify_model


PUBLIC_STUDY_LIMIT = 64 * 1024**2  # the lab gives a public link only for dataset files up to this size


def private_reachable(url, timeout=4):
    parsed = urlsplit(url)
    try:
        socket.create_connection((parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80)), timeout)
    except OSError:
        return False
    return True


def transfer(agent, assignment, digest, target, limit, reachable=private_reachable):
    target = Path(target)
    if target.is_file():
        with target.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() == digest:
                return target
        raise ValueError("Cached study file checksum mismatch")
    grant = agent.call(
        "/api/v1/device/model-transfer" if "jobId" in assignment else "/api/v1/device/study-transfer",
        {"jobId": assignment["jobId"], "sha256": digest}
        if "jobId" in assignment
        else {"assignmentId": assignment["assignmentId"], "epoch": assignment["epoch"], "sha256": digest},
    )
    url = grant["url"]
    parsed = urlsplit(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    # Reuse transport validation: a large file never goes through a public URL ...
    from heteroes.http_transport import HttpClient

    HttpClient(origin, bulk_url=origin)
    public = grant.get("publicUrl")
    if public and limit <= PUBLIC_STUDY_LIMIT and not reachable(url):
        # ... except a small dataset file, over the lab's own HTTPS address, for a device without the private route
        # (Tailscale off); its bytes are still checked against the pinned SHA-256 below
        if urlsplit(public).scheme != "https":
            raise ValueError("A public study link must use HTTPS")
        url = public
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(prefix=".pending-", dir=target.parent)
    temporary = Path(name)
    try:
        hasher = hashlib.sha256()
        total = 0
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=120) as response, os.fdopen(fd, "wb") as out:
            while chunk := response.read(1024**2):
                total += len(chunk)
                if total > limit:
                    raise ValueError("Study transfer exceeds its bound")
                hasher.update(chunk)
                out.write(chunk)
            out.flush()
            os.fsync(out.fileno())
        if hasher.hexdigest() != digest:
            raise ValueError("Study transfer checksum mismatch")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def study_cache(agent):
    from heteroes.product.storage import checked_directory

    # the volume identity belongs to the large-data directory; the default cache is in the agent's private state
    large = agent.config.get("largeDataDirectory")
    return (
        checked_directory(large, agent.config.get("storageVolumeUUID")) if large else agent.root / "study-cache"
    ) / "study"


def prepare(agent, assignment, config, directory):
    cache = study_cache(agent)
    data_path = transfer(
        agent,
        assignment,
        config["datasetObjectSha256"],
        cache / "datasets" / f"{config['datasetObjectSha256']}.json",
        10_000_000,
    )
    if config.get("recipeVersion") == 3:
        from heteroes.v3.data import open_dataset, split_files, verify as verify_dataset

        # a file-backed dataset (format 3): its split files, each pinned by the document, go beside it
        for digest, size in split_files(verify_dataset(json.loads(data_path.read_text()))).items():
            transfer(agent, assignment, digest, data_path.parent / f"{digest}.jsonl", size)
        data = open_dataset(data_path)
    else:
        data = verify_data(json.loads(data_path.read_text()))
    if {k: data[k] for k in ("contentHash", "splitHashes")} != config["datasetIdentity"]:
        raise ValueError("Frozen dataset identity mismatch")
    model_path = prepare_model(agent, assignment, config)
    manifest = config["modelManifest"]
    from heteroes.product.files import write_json

    directory = Path(directory)
    write_json(directory / "model-manifest.json", manifest)
    return {
        "modelPath": str(model_path),
        "datasetPath": str(data_path),
        "modelManifestPath": str(directory / "model-manifest.json"),
    }


def prepare_model(agent, assignment, config, emit=lambda event: None):
    """Pin/verify model bytes independently of datasets, also for a trusted model compatibility probe."""
    cache = study_cache(agent)
    manifest = config["modelManifest"]
    # Operator paths are private configuration, never browser-supplied paths.
    model_path = agent.config.get("modelPaths", {}).get(sha(manifest))
    if not model_path and manifest["modelId"] == PINNED_MODEL_ID and manifest["revision"] == PINNED_REVISION:
        model_path = agent.config["modelPath"]
    if not model_path:
        model_path = cache / "models" / sha(manifest)
        for name, digest in manifest["files"].items():
            emit({"stage": "model_file"})
            target = Path(model_path) / name
            if config["modelSource"] == "UPLOAD":
                transfer(agent, assignment, digest, target, 5_000_000_000)
            else:
                from huggingface_hub import hf_hub_download

                hf_hub_download(manifest["modelId"], name, revision=manifest["revision"], local_dir=model_path)
    if config.get("recipeVersion") == 3:
        from .models import verify_files

        verify_files(model_path, manifest["files"])
    else:
        verify_model(model_path, manifest)
    return Path(model_path)
