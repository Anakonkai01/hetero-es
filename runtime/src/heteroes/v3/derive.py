"""
Continue from an earlier run: turn the verified weights of one of its recovery points into a new pinned model directory.

The new directory holds the base model's configuration and tokenizer files, a `model.safetensors` with the trained
weights and a `heteroes-lineage.json` that names the source (run, point, generation, weights SHA-256). The lineage file is
one of the model's pinned files, so it is part of the new model's identity: every device checks it with the rest.

A run on the derived model is an ordinary run with its own recipe: alpha, sigma, data, scorer and generations may all
change. Its generation 0 parent is, bit for bit, the source weights (checked here before the directory is published).
Optimizer state (momentum, schedules) and the source run's generation numbering do not carry over.
"""

import hashlib
import json
import os
import shutil
import sqlite3
import urllib.request
import uuid
from pathlib import Path

from heteroes.canonical import canonical_json_hash

LINEAGE_FILE = "heteroes-lineage.json"
LINEAGE_VERSION = 1
_WEIGHT_FILES = ("model.safetensors.index.json",)


def _final_applied(ledger_path):
    with sqlite3.connect(f"file:{ledger_path}?mode=ro", uri=True) as db:
        row = db.execute(
            "SELECT generation, child_weights_sha256 FROM generation_update"
            " WHERE applied_at IS NOT NULL ORDER BY generation DESC LIMIT 1"
        ).fetchone()
    if row is None:
        raise ValueError("the run has no applied generation to continue from")
    return int(row[0]), row[1]


def local_source(run_dir):
    """The last applied generation of a run made on this machine (`python -m heteroes.v3 run`)."""
    run_dir = Path(run_dir)
    recipe = json.loads((run_dir / "recipe.json").read_text())
    generation, sha = _final_applied(run_dir / "ledger.sqlite")
    weights = run_dir / "published" / f"{sha}.bin"
    if not weights.is_file():
        raise ValueError(f"the published weights {sha}.bin of generation {generation} are missing")
    return {
        "recipe": recipe,
        "weights": weights,
        "sha256": sha,
        "source": {"kind": "local", "runDirectory": run_dir.name, "generation": generation},
    }


def _download(url, target, sha256, size):
    """A signed storage URL (no lab credential) into `target`, checked against its size and SHA-256."""
    from heteroes.http_safety import opener
    from heteroes.http_transport import USER_AGENT

    target = Path(target)
    temporary = target.with_name(target.name + ".pending-" + uuid.uuid4().hex)
    try:
        digest, total = hashlib.sha256(), 0
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with temporary.open("xb") as out, opener(proxy=False).open(request, timeout=600) as response:
            while chunk := response.read(1 << 20):
                total += len(chunk)
                if total > size:
                    raise ValueError(f"{target.name} is larger than its manifest says")
                digest.update(chunk)
                out.write(chunk)
        if total != size or digest.hexdigest() != sha256:
            raise ValueError(f"{target.name} does not match its manifest")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def choose_point(points, point_id=None):
    """The requested point, else the newest verified one (the final point when it is the newest); only READY qualify."""
    ready = [p for p in points if p.get("status") == "READY"]
    if point_id is not None:
        chosen = next((p for p in points if p.get("pointId") == point_id), None)
        if chosen is None:
            raise ValueError(f"recovery point {point_id} does not belong to this run")
        if chosen.get("status") != "READY":
            raise ValueError(f"recovery point {point_id} is {chosen.get('status')}, not READY")
        return chosen
    if not ready:
        raise ValueError("the run has no verified (READY) recovery point")
    # The newest generation wins; a final point only breaks a tie. An older point marked final (a paused run's point
    # before 25/11) never outranks newer weights, and a final point still being verified is waited for, never
    # silently replaced by an older verified one.
    newest = max(points, key=lambda p: (p["generation"], bool(p.get("final"))))
    if newest.get("final") and newest.get("status") != "READY":
        raise ValueError(
            f"the run's final point (generation {newest['generation']}) is {newest.get('status')}, not READY yet"
        )
    return max(ready, key=lambda p: (p["generation"], bool(p.get("final"))))


def lab_source(api, run_id, directory, point_id=None, download=_download):
    """Fetch a verified recovery point of a lab run: its recipe and its child weights, both checked by SHA-256."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    point = choose_point(api.request("GET", f"/api/v1/experiments/{run_id}/recovery-points"), point_id)
    plan = api.request("POST", f"/api/v1/recovery-points/{point['pointId']}/download-plan")
    manifest = plan["manifest"]
    if manifest["runId"] != run_id or manifest["pointId"] != point["pointId"]:
        raise ValueError("the lab returned another recovery point")
    sha = manifest["childWeightsSha256"]
    wanted = {"identity.json": directory / "identity.json", f"weights/{sha}.bin": directory / f"{sha}.bin"}
    for name, target in wanted.items():
        meta = manifest["files"].get(name)
        if meta is None or name not in plan["objects"]:
            raise ValueError(f"the recovery point has no {name}")
        if not (target.is_file() and target.stat().st_size == meta["sizeBytes"] and _sha256(target) == meta["sha256"]):
            target.unlink(missing_ok=True)
            download(plan["objects"][name], target, meta["sha256"], meta["sizeBytes"])
    return {
        "recipe": json.loads(wanted["identity.json"].read_text())["recipe"],
        "weights": wanted[f"weights/{sha}.bin"],
        "sha256": sha,
        "source": {
            "kind": "lab",
            "runId": run_id,
            "pointId": point["pointId"],
            "generation": manifest["generation"],
            "final": bool(manifest.get("final")),
        },
    }


def _sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def derive_model(base_path, source, out):
    """
    Write the derived model directory `out` (must not exist) from the base model of the source run and the source
    weights; returns {"path", "files", "lineage"}. The base directory must be exactly the run's pinned model files.
    """
    import torch
    from safetensors.torch import save_model

    from heteroes.eval.candidate import model_weights_sha256
    from heteroes.model.weights_io import load_weights_
    from heteroes.v3.model import file_manifest, load, trainable_schema

    recipe, sha = source["recipe"], source["sha256"]
    if recipe.get("formatVersion") != 3:
        raise ValueError("only Recipe v3 runs can be continued")
    space = recipe["weightSpace"]
    if space["kind"] not in ("full", "subset"):
        raise ValueError("a LoRA run keeps only its adapters: continuing it needs the adapter path, not supported yet")
    base_path, out = Path(base_path), Path(out)
    if out.exists():
        raise FileExistsError(out)
    base_files = file_manifest(base_path)
    if base_files != recipe["model"]["files"]:
        raise ValueError("the base model directory is not the model the source run pinned")
    model, _ = load(base_path, base_files)
    schema = trainable_schema(model, space)
    if schema.hash != recipe["schemaHash"]:
        raise ValueError("the base model's trainable schema differs from the source run's")
    load_weights_(model, schema, source["weights"], sha)
    parent = None
    if LINEAGE_FILE in base_files:
        parent = json.loads((base_path / LINEAGE_FILE).read_text())
    lineage = {
        "formatVersion": LINEAGE_VERSION,
        "base": {
            "modelId": recipe["model"]["id"],
            "revision": recipe["model"]["revision"],
            "filesHash": canonical_json_hash(base_files),
        },
        "weightsSha256": sha,
        "schemaHash": schema.hash,
        "weightSpace": space,
        "source": source["source"],
        "parent": parent,
    }
    staging = out.with_name(out.name + ".partial-" + uuid.uuid4().hex)
    staging.mkdir(parents=True, mode=0o700)
    try:
        for name in base_files:
            if name.endswith(".safetensors") or name in _WEIGHT_FILES or name == LINEAGE_FILE:
                continue
            (staging / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(base_path / name, staging / name)
        with torch.no_grad():
            save_model(model, str(staging / "model.safetensors"), metadata={"format": "pt"})
        (staging / LINEAGE_FILE).write_text(json.dumps(lineage, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        del model
        files = file_manifest(staging)
        derived, _ = load(staging, files)
        if model_weights_sha256(derived, trainable_schema(derived, space)) != sha:
            raise ValueError("the derived model does not reproduce the source weights")
        os.rename(staging, out)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return {"path": str(out), "files": files, "lineage": lineage}


def read_lineage(model_path):
    """The lineage of a derived model directory, or None for a model that was not derived from a run."""
    path = Path(model_path) / LINEAGE_FILE
    return json.loads(path.read_text()) if path.is_file() else None
